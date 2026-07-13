"""Hermetic replay backend — the source-or-silence regression gate (Epic 009,
golden-trip + cassette half).

Runs the REAL engine (`plan_from_origin`: scout → drive-prefilter → verify →
guardrails — the exact production code path) against a recorded world: a corpus
fixture served through the real `ScopedSession` seam (rule #4 — never a
privileged bypass) and the live adapters replayed from recorded cassettes
through `httpx.MockTransport` (zero network; an unmatched URL raises loudly).
Every criterion is a code predicate against the typed output + the captured
bundle — no judge decides an invariant (Stage-7 §4.1: truthfulness is tested by
something that itself can't hallucinate).

Scenario layout (Epic 009 AC-2.1): `evals/scenarios/<name>/` holding
`intent.json` + `viewer.json` + `corpus.json` + `conditions/<adapter>.json`
(the cassette bundle — fixture artifacts, never graph nodes, rule #3) +
`expected.json` (hard expectations only; the soft/judge half is deferred with
the LLM-judge — see the Epic 009 header note).

Deferred by design (not built here): the LLM-judge (`ScoredJudge`), the Brier
calibration hook, and the N-run provider matrix — this gate is deterministic
(no LLM in the loop), so N>1 exists only to prove run-to-run stability of the
replay itself.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from evals.truthfulness import (
    CriterionResult,
    EvalReport,
    no_blocked_surfaced,
    source_or_silence_ok,
)
from graph.client import ScopedSession
from orchestration.adapters.airnow import AirNowAdapter
from orchestration.adapters.base import ConditionKind, LiveAdapter
from orchestration.adapters.firms import FirmsAdapter
from orchestration.adapters.nps_alerts import NpsAlertsAdapter
from orchestration.adapters.nws import NwsAdapter
from orchestration.adapters.registry import TTLCache
from orchestration.adapters.ridb import RidbAdapter
from orchestration.adapters.usgs_water import UsgsWaterAdapter
from orchestration.engine import (
    PlannedBatch,
    PlannedTrail,
    SetAsideTrail,
    feed_card,
    plan_from_origin,
)
from orchestration.two_phase import verify_planned

SCENARIOS_DIR = Path(__file__).resolve().parent / "scenarios"

# Placeholder credentials for keyed adapters: the cassette player answers every
# request, so no key is ever sent anywhere (and rule #10 keeps real ones out).
_ADAPTER_BUILDERS: dict[str, Callable[[httpx.Client], LiveAdapter]] = {
    "nws": lambda c: NwsAdapter("adventure-planner eval-replay", client=c),
    "airnow": lambda c: AirNowAdapter("eval-replay-not-a-key", client=c),
    "firms": lambda c: FirmsAdapter("eval-replay-not-a-key", client=c),
    "usgs_water": lambda c: UsgsWaterAdapter(client=c),
    "ridb": lambda c: RidbAdapter("eval-replay-not-a-key", client=c),
    "nps_alerts": lambda c: NpsAlertsAdapter("eval-replay-not-a-key", client=c),
}


@dataclass(frozen=True)
class ReplayScenario:
    """One golden trip: a pinned world + conditions bundle + hard expectations."""

    name: str
    intent: dict[str, Any]
    viewer: dict[str, Any]
    corpus: dict[str, Any]
    conditions: dict[str, dict[str, Any]]  # adapter name -> cassette doc
    expected: dict[str, Any]


def list_scenario_dirs() -> list[Path]:
    return sorted(p for p in SCENARIOS_DIR.iterdir() if (p / "intent.json").exists())


def load_scenario(path: Path) -> ReplayScenario:
    def _read(name: str) -> dict[str, Any]:
        doc = json.loads((path / name).read_text(encoding="utf-8"))
        assert isinstance(doc, dict)
        return doc

    conditions: dict[str, dict[str, Any]] = {}
    cond_dir = path / "conditions"
    if cond_dir.is_dir():
        for cassette in sorted(cond_dir.glob("*.json")):
            doc = json.loads(cassette.read_text(encoding="utf-8"))
            conditions[cassette.stem] = doc
    return ReplayScenario(
        name=path.name,
        intent=_read("intent.json"),
        viewer=_read("viewer.json"),
        corpus=_read("corpus.json"),
        conditions=conditions,
        expected=_read("expected.json"),
    )


# ── the cassette player (mirrors tests/test_adapter_cassettes.py) ─────────────


def _player(cassette: dict[str, Any]) -> httpx.Client:
    """A client whose transport answers each request from the first interaction whose
    `match` substring appears in the URL. An unmatched request raises loudly — the
    no-network guard: nothing in a replay run can silently reach a live service."""
    interactions = cassette["interactions"]

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for it in interactions:
            if it["match"] in url:
                if "json" in it:
                    return httpx.Response(it["status"], json=it["json"])
                return httpx.Response(it["status"], text=it["text"])
        raise AssertionError(f"cassette {cassette.get('adapter')!r} has no match for {url!r}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def build_probes(scenario: ReplayScenario) -> dict[ConditionKind, list[LiveAdapter]]:
    """The scenario's recorded fan-out: only cassette-backed adapters exist, so a
    kind with no cassette is genuinely un-probed (`probed_kinds` stays honest)."""
    grouped: dict[ConditionKind, list[LiveAdapter]] = {}
    for name, cassette in scenario.conditions.items():
        builder = _ADAPTER_BUILDERS.get(name)
        if builder is None:
            known = ", ".join(sorted(_ADAPTER_BUILDERS))
            raise ValueError(f"scenario {scenario.name!r}: unknown adapter {name!r} ({known})")
        adapter = builder(_player(cassette))
        grouped.setdefault(adapter.kind, []).append(adapter)
    return grouped


# ── the corpus fixture served through the REAL access seam (rule #4) ──────────


def corpus_session(scenario: ReplayScenario) -> ScopedSession:
    """A real `ScopedSession` (same class production uses; `$viewer_id` merged into
    every read) whose runner serves the scenario's pinned corpus rows. Dispatch keys
    on the query builders' own load-bearing clauses, so a new read path added to the
    engine fails loudly here instead of silently returning []."""
    corpus = scenario.corpus

    def runner(cypher: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if "SAME_AS" in cypher:
            rows = corpus.get("corroboration", [])
        elif "MATCH (h:Trailhead)" in cypher:
            rows = corpus.get("trailhead_rows", [])
        elif "WHERE t.point IS NOT NULL" in cypher:
            rows = corpus.get("direct_rows", [])
        else:
            raise AssertionError(
                f"scenario {scenario.name!r}: corpus fixture has no handler for query:\n{cypher}"
            )
        assert isinstance(rows, list)
        return rows

    return ScopedSession(
        scenario.viewer.get("viewer_id", "anonymous"),
        list(scenario.viewer.get("granted_ids", [])),
        runner,
    )


def run_scenario(scenario: ReplayScenario) -> PlannedBatch:
    """One REAL-engine pass over the recorded world. A fresh TTLCache per run keeps
    runs independent; live facts stay in-process, never persisted (rule #3)."""
    intent = scenario.intent
    return plan_from_origin(
        float(intent["lat"]),
        float(intent["lon"]),
        corpus_session(scenario),
        build_probes(scenario),
        radius_m=float(intent.get("radius_m", 40_000.0)),
        k=int(intent.get("k", 10)),
        cache=TTLCache(),
    )


def run_scenario_two_phase(
    scenario: ReplayScenario,
) -> tuple[PlannedBatch, list[PlannedTrail], list[SetAsideTrail]]:
    """The Epic 040 split over the same recorded world: phase 1 (`verify=False` —
    zero probes, every kind `not_fetched`), then the phase-2 fold through the SAME
    `verify_planned` production serves. Returns `(phase1, composed, removed)` for
    the D3 criteria below."""
    intent = scenario.intent
    origin = (float(intent["lat"]), float(intent["lon"]))
    phase1 = plan_from_origin(
        origin[0],
        origin[1],
        corpus_session(scenario),
        # No adapters AT ALL on the phase-1 pass: probing is structurally
        # impossible here, not merely skipped — the no-network guarantee for
        # phase 1 is by construction.
        {},
        radius_m=float(intent.get("radius_m", 40_000.0)),
        k=int(intent.get("k", 10)),
        cache=TTLCache(),
        verify=False,
    )
    composed, removed = verify_planned(
        phase1.trails, origin, build_probes(scenario), cache=TTLCache()
    )
    return phase1, composed, removed


# ── hard-expectation checks: each returns violation strings (empty == pass) ───


# Every scenario must state EVERY expectation explicitly — an omitted or typo'd key
# would otherwise default to its empty expectation and pass vacuously, the exact
# quiet-green this gate exists to prevent (self-review finding, 2026-07-11).
_REQUIRED_HARD_KEYS = frozenset(
    {
        "min_cards",
        "must_be_blocked",
        "allowed_kinds",
        "facts",
        "corpus_corroboration",
        "expected_warnings",
        "expected_unavailable_kinds",
        "region_wide_warnings",
        "condition_states",
    }
)

# The per-kind disposition vocabulary (Epic 018 S4 / CDP-02) — mirrors
# `orchestration.engine.ConditionStatus`. Kept here as a literal so a fixture typo
# ("no_hazrd") reds the scenario with a named violation instead of passing vacuously.
_CONDITION_STATES = frozenset(
    {"present", "stale_degraded", "no_hazard", "no_data", "unavailable", "not_fetched"}
)

# States where a source actually ANSWERED: the status must carry source + checked_at
# (sourced silence / sourced fact). The complement must carry neither — an unanswered
# kind wearing a source would be a fabricated attribution (rule #1).
_ANSWERED_STATES = frozenset({"present", "stale_degraded", "no_hazard", "no_data"})


def _hard(scenario: ReplayScenario) -> dict[str, Any]:
    hard = scenario.expected.get("hard")
    if not isinstance(hard, dict):
        raise ValueError(f"scenario {scenario.name!r}: expected.json has no 'hard' object")
    keys = set(hard.keys())
    if keys != _REQUIRED_HARD_KEYS:
        missing = sorted(_REQUIRED_HARD_KEYS - keys)
        unknown = sorted(keys - _REQUIRED_HARD_KEYS)
        raise ValueError(
            f"scenario {scenario.name!r}: expected.json hard block is malformed —"
            f" missing keys {missing}, unknown keys {unknown}. Every expectation must"
            " be stated explicitly (an explicit empty value is a deliberate choice;"
            " an absent key would pass vacuously)."
        )
    return hard


def check_surfaced_expected(batch: PlannedBatch, hard: dict[str, Any]) -> list[str]:
    """Guards the vacuous pass: source-or-silence trivially holds on an empty feed,
    so a scenario must state how many cards the bundle should yield."""
    min_cards = int(hard.get("min_cards", 0))
    if len(batch.trails) < min_cards:
        return [f"expected >= {min_cards} surfaced trails, got {len(batch.trails)}"]
    return []


def check_must_be_blocked(batch: PlannedBatch, hard: dict[str, Any]) -> list[str]:
    """AC-4.3(b)/AC-3.2: the must-be-blocked set is a hand label in the cassette,
    never a re-run of guardrail code — every labeled trail must be set aside with a
    sourced reason and must never surface."""
    out: list[str] = []
    surfaced = {t.candidate.canonical_id for t in batch.trails}
    set_aside = {t.canonical_id: t for t in batch.set_aside}
    for cid in hard.get("must_be_blocked", []):
        if cid in surfaced:
            out.append(f"labeled must-be-blocked trail {cid!r} SURFACED")
        elif cid not in set_aside:
            out.append(f"labeled must-be-blocked trail {cid!r} neither surfaced nor set aside")
        elif not all(r.source for r in set_aside[cid].reasons):
            out.append(f"set-aside {cid!r} carries an unsourced reason")
    return out


def check_fact_fidelity(batch: PlannedBatch, hard: dict[str, Any]) -> list[str]:
    """AC-4.2 (pre-card fidelity): every surfaced fact of an expected kind must equal
    what the recorded adapter returned — source prefix + the pinned value subset.
    At least one trail must carry the kind, or the check would pass vacuously."""
    out: list[str] = []
    for kind_name, spec in hard.get("facts", {}).items():
        try:
            kind = ConditionKind(kind_name)
        except ValueError:
            # A fixture typo ("wether") reds this criterion with a named violation
            # rather than aborting the whole scenario walk with a traceback.
            known = ", ".join(k.value for k in ConditionKind)
            out.append(f"expected.json names unknown condition kind {kind_name!r} ({known})")
            continue
        carriers = [t for t in batch.trails if kind in t.facts]
        if not carriers:
            out.append(f"no surfaced trail carries expected kind {kind_name!r}")
            continue
        for trail in carriers:
            fact = trail.facts[kind]
            prefix = spec.get("source_prefix")
            if prefix and not fact.source.startswith(prefix):
                out.append(f"{kind_name} source {fact.source!r} != prefix {prefix!r}")
            expected_value = spec.get("value", {})
            actual = fact.value if isinstance(fact.value, dict) else {}
            for key, want in expected_value.items():
                got = actual.get(key)
                if got != want:
                    out.append(f"{kind_name}.{key}: recorded {want!r}, surfaced {got!r}")
    return out


def check_no_fabricated_kinds(batch: PlannedBatch, hard: dict[str, Any]) -> list[str]:
    """AC-4.5 (source-or-silence's contrapositive): a kind the bundle can't verify
    (adapter absent, outage, empty return) must be absent — surfaced facts are a
    subset of what the recorded adapters actually returned."""
    allowed = set(hard.get("allowed_kinds", []))
    out: list[str] = []
    for trail in batch.trails:
        for kind in trail.facts:
            if kind.value not in allowed:
                out.append(
                    f"trail {trail.candidate.canonical_id!r} surfaced fabricated kind"
                    f" {kind.value!r} (bundle allows {sorted(allowed)})"
                )
    return out


def check_corroboration_wired(batch: PlannedBatch, hard: dict[str, Any]) -> list[str]:
    """CDP-01 stays wired: the distinct-origin count read from the corpus SAME_AS
    layer reaches the plan (a regression back to the constant-1 axis fails here)."""
    expected: dict[str, int] = hard.get("corpus_corroboration", {})
    by_id = {t.candidate.canonical_id: t for t in batch.trails}
    out: list[str] = []
    for cid, want in expected.items():
        trail = by_id.get(cid)
        if trail is None:
            out.append(f"corroboration-pinned trail {cid!r} not surfaced")
        elif trail.corpus_corroboration != want:
            out.append(f"{cid}: corpus_corroboration {trail.corpus_corroboration} != pinned {want}")
    return out


def check_warnings_expected(batch: PlannedBatch, hard: dict[str, Any]) -> list[str]:
    """A VERIFIED hazard shows, never hides (2026-07-01): each expected warning must
    appear, source-stamped, on at least one surfaced card."""
    out: list[str] = []
    for needle in hard.get("expected_warnings", []):
        hit = any(needle in w.text and w.source for t in batch.trails for w in t.verdict.warnings)
        if not hit:
            out.append(f"expected warning containing {needle!r} not found on any card")
    return out


def check_unavailable_disclosed(batch: PlannedBatch, hard: dict[str, Any]) -> list[str]:
    """Rule #1 + #6: a probed-but-silent condition is DISCLOSED as unverifiable on
    the card — never dropped silently, never fabricated as clear."""
    out: list[str] = []
    for kind_name in hard.get("expected_unavailable_kinds", []):
        hit = any(u.kind == kind_name for t in batch.trails for u in t.verdict.unavailable)
        if not hit:
            out.append(f"expected an unavailable-condition disclosure for {kind_name!r}")
    return out


def check_verdict_consistency(batch: PlannedBatch, hard: dict[str, Any]) -> list[str]:
    """One sky, one verdict (ux-review-conditions-2026-07 F1): a region-wide alert
    must ride EVERY surfaced card's own warning set, source-stamped — not just the
    feed banner. The card verdict and the Detail verdict are both derived from the
    same per-card payload on the surface, so this is the wire-level invariant that
    makes them provably equal: if the alert reached only some cards, a card without
    it would say "Good to go" while the banner (and its own Detail) said "Caution" —
    the live-DOM contradiction this gate now pins (Ocracoke, 2026-07-12)."""
    expected = hard.get("region_wide_warnings", [])
    if expected and not batch.trails:
        # Non-empty pins with zero surfaced cards must not quiet-green (the same
        # vacuous-pass class the condition_states guard closes): there is no card
        # to carry the alert, so the invariant was never exercised.
        return ["region_wide_warnings pinned but no trail surfaced to carry them"]
    out: list[str] = []
    for needle in expected:
        for trail in batch.trails:
            cid = trail.candidate.canonical_id
            if not any(needle in w.text and w.source for w in trail.verdict.warnings):
                out.append(f"{cid}: region-wide warning {needle!r} missing from this card")
    return out


def check_condition_states(batch: PlannedBatch, hard: dict[str, Any]) -> list[str]:
    """CDP-02 at the gate (Epic 018 S4f): every surfaced card's per-kind disposition
    must match the pinned state, through the same `feed_card` path production serves.
    This is what keeps an ANSWERED clear (no_hazard / no_data — sourced silence)
    permanently distinct from couldn't-verify (unavailable), and locks in the #160
    self-review bug: a parse failure must never surface as an answered no-data —
    pinning `unavailable` here fails if the engine ever fabricates a sourced answer.
    An answered state must carry source + checked_at; an unanswered one must carry
    neither (a source on an unanswered kind is a fabricated attribution, rule #1)."""
    expected: dict[str, str] = hard.get("condition_states", {})
    out: list[str] = []
    known_kinds = {k.value for k in ConditionKind}
    for kind, want in expected.items():
        if kind not in known_kinds:
            out.append(f"expected.json names unknown condition kind {kind!r}")
        if want not in _CONDITION_STATES:
            out.append(
                f"expected.json pins unknown condition state {want!r} for {kind!r}"
                f" ({', '.join(sorted(_CONDITION_STATES))})"
            )
    if out or not expected:
        return out
    if not batch.trails:
        # Non-empty pins with zero surfaced cards must not quiet-green: there is
        # nothing to check the pins against (the vacuous-pass class the required-
        # keys mechanism exists to prevent). A blocked-feed scenario states an
        # explicit empty `condition_states` instead.
        return ["condition_states pinned but no trail surfaced to carry them"]
    for trail in batch.trails:
        cid = trail.candidate.canonical_id
        by_kind = {c.kind: c for c in feed_card(trail).conditions}
        for kind, want in expected.items():
            status = by_kind.get(kind)
            if status is None:
                out.append(f"{cid}: card carries no condition status for {kind!r}")
                continue
            if status.state != want:
                out.append(f"{cid}: {kind} state {status.state!r} != pinned {want!r}")
                continue
            answered = bool(status.source) and status.checked_at is not None
            if want in _ANSWERED_STATES and not answered:
                out.append(f"{cid}: {kind} {want!r} lacks source/checked_at (unsourced answer)")
            if want not in _ANSWERED_STATES and answered:
                out.append(f"{cid}: {kind} {want!r} carries a fabricated source attribution")
    return out


# ── Epic 040 D3: two-phase criteria (code predicates, no judge) ───────────────
#
# Every scenario's recorded bundle runs through BOTH paths each evaluation run:
# the classic single pass (`run_scenario`) and the split (`run_scenario_two_phase`).
# The three criteria below hold the split to the single-pass truth — a drift reds
# CI with a named violation, not a rate.

# Point kinds a phase-1 plan may never carry a fact for. drive_time is exempt: it
# is origin-relative (the drive prefilter is deliberately part of phase 1 — Epic
# 040 S1), not a live point condition.
_POINT_KINDS = frozenset(k for k in ConditionKind if k is not ConditionKind.drive_time)


def check_phase1_silence(phase1: PlannedBatch) -> list[str]:
    """D3.1 — the phase-1 batch fabricates nothing: zero point-kind facts, every
    disposition `not_fetched` with no attribution, zero warnings, zero unavailable
    disclosures, zero set-asides. Silence before verification, never a guess."""
    out: list[str] = []
    if phase1.set_aside:
        held = [t.canonical_id for t in phase1.set_aside]
        out.append(f"phase 1 set aside {held} before anything was verified")
    for trail in phase1.trails:
        cid = trail.candidate.canonical_id
        fabricated = sorted(k.value for k in trail.facts if k in _POINT_KINDS)
        if fabricated:
            out.append(f"{cid}: phase 1 carries point-kind facts {fabricated}")
        if trail.verdict.warnings:
            out.append(f"{cid}: phase 1 wears warnings before verification")
        if trail.verdict.unavailable:
            out.append(f"{cid}: phase 1 discloses unavailable kinds nothing probed")
        card = feed_card(trail)
        if any(line.text for line in card.lines):
            drive_only = all("drive" in line.text.lower() for line in card.lines)
            if not drive_only:
                out.append(f"{cid}: phase 1 renders condition lines")
        for status in card.conditions:
            if status.state != "not_fetched":
                out.append(f"{cid}: {status.kind} phase-1 state {status.state!r}")
            if status.source or status.checked_at is not None:
                out.append(f"{cid}: {status.kind} phase-1 carries a fabricated attribution")
    return out


def check_two_phase_composition(
    single: PlannedBatch,
    phase1: PlannedBatch,
    composed: list[PlannedTrail],
    removed: list[SetAsideTrail],
) -> list[str]:
    """D3.2 — phase 1 + the conditions patch, composed, is equivalent to the
    single-pass output over the same bundle: same surfaced trail set, same
    per-kind facts (source + value), same six-state dispositions (incl. the
    sourced/unsourced attribution contract), same warnings, same unavailable
    disclosures, same set-asides, same notices. Two phases are a presentation
    split, never a second truth. (Order is deliberately NOT compared here —
    `check_phase_order_stable` owns ordering, per D5.)"""
    out: list[str] = []
    single_by_id = {t.candidate.canonical_id: t for t in single.trails}
    composed_by_id = {t.candidate.canonical_id: t for t in composed}
    if set(single_by_id) != set(composed_by_id):
        out.append(
            f"surfaced set drifted: single-pass {sorted(single_by_id)} !="
            f" composed {sorted(composed_by_id)}"
        )
        return out
    single_aside = {t.canonical_id: t for t in single.set_aside}
    composed_aside = {t.canonical_id: t for t in (*phase1.set_aside, *removed)}
    if set(single_aside) != set(composed_aside):
        out.append(
            f"set-aside set drifted: single-pass {sorted(single_aside)} !="
            f" composed {sorted(composed_aside)}"
        )
    for cid, aside in single_aside.items():
        other_aside = composed_aside.get(cid)
        if other_aside is None:
            continue
        s_reasons = [(r.kind, r.text, r.source) for r in aside.reasons]
        c_reasons = [(r.kind, r.text, r.source) for r in other_aside.reasons]
        if s_reasons != c_reasons:
            out.append(f"{cid}: set-aside reasons drifted {c_reasons} != {s_reasons}")
    if tuple(single.notices) != tuple(phase1.notices):
        out.append(f"notices drifted: {list(phase1.notices)} != {list(single.notices)}")
    render_now = datetime.now(timezone.utc)
    for cid, s_trail in single_by_id.items():
        c_trail = composed_by_id[cid]
        my_facts = {k.value: f for k, f in s_trail.facts.items()}
        other_facts = {k.value: f for k, f in c_trail.facts.items()}
        if set(my_facts) != set(other_facts):
            out.append(f"{cid}: fact kinds drifted {sorted(other_facts)} != {sorted(my_facts)}")
            continue
        for kind, fact in my_facts.items():
            got = other_facts[kind]
            if got.source != fact.source or got.value != fact.value:
                out.append(f"{cid}: {kind} fact drifted (source/value)")
        my_card = feed_card(s_trail, now=render_now)
        other_card = feed_card(c_trail, now=render_now)
        my_states = [
            (s.kind, s.state, s.source, s.checked_at is not None) for s in my_card.conditions
        ]
        other_states = [
            (s.kind, s.state, s.source, s.checked_at is not None) for s in other_card.conditions
        ]
        if my_states != other_states:
            out.append(f"{cid}: dispositions drifted {other_states} != {my_states}")
        my_warn = [(w.kind, w.text, w.source) for w in s_trail.verdict.warnings]
        other_warn = [(w.kind, w.text, w.source) for w in c_trail.verdict.warnings]
        if my_warn != other_warn:
            out.append(f"{cid}: warnings drifted {other_warn} != {my_warn}")
        my_unavail = [(u.kind, u.reason, u.source) for u in s_trail.verdict.unavailable]
        other_unavail = [(u.kind, u.reason, u.source) for u in c_trail.verdict.unavailable]
        if my_unavail != other_unavail:
            out.append(f"{cid}: unavailable disclosures drifted {other_unavail} != {my_unavail}")
    return out


def check_phase_order_stable(
    phase1: PlannedBatch, composed: list[PlannedTrail], removed: list[SetAsideTrail]
) -> list[str]:
    """D3.3 / D5 — the composed card order is the phase-1 order minus phase-2
    removals: nothing ever reshuffles under the user's eyes."""
    removed_ids = {t.canonical_id for t in removed}
    want = [
        t.candidate.canonical_id
        for t in phase1.trails
        if t.candidate.canonical_id not in removed_ids
    ]
    got = [t.candidate.canonical_id for t in composed]
    if got != want:
        return [f"composed order {got} != phase-1 order minus removals {want}"]
    return []


# The D3 criteria names (Epic 040 S4 AC-4.1). Run alongside — never instead of —
# the single-pass `_CHECKS`: the classic path stays gated (it remains the D6
# fallback and the old-client contract).
_TWO_PHASE_CRITERIA = ("phase1_silence", "two_phase_composition", "phase_order_stable")

_CHECKS: list[tuple[str, Callable[[PlannedBatch, dict[str, Any]], list[str]]]] = [
    ("surfaced_expected", check_surfaced_expected),
    ("must_be_blocked_held", check_must_be_blocked),
    ("fact_fidelity", check_fact_fidelity),
    ("no_fabricated_kinds", check_no_fabricated_kinds),
    ("corroboration_wired", check_corroboration_wired),
    ("warnings_expected", check_warnings_expected),
    ("unavailable_disclosed", check_unavailable_disclosed),
    ("verdict_consistency", check_verdict_consistency),
    ("condition_states", check_condition_states),
]


@dataclass(frozen=True)
class ScenarioResult:
    report: EvalReport
    # First failing run's violation strings per criterion (AC-6.4: an invariant
    # failure surfaces a reproduction, not a number to watch trend down).
    failures: dict[str, list[str]]

    @property
    def passed(self) -> bool:
        return self.report.passed(threshold=1.0)


def evaluate_scenario(scenario: ReplayScenario, n: int = 3) -> ScenarioResult:
    """N REAL-engine runs; every criterion is a zero-tolerance invariant (a 19/20 is
    a P0 with a reproduction, not a B+ — AC-4.6). The flow is deterministic without
    an LLM in the loop, so N here proves replay stability, not sampling spread."""
    counts: dict[str, int] = {"source_or_silence": 0, "no_blocked_surfaced": 0}
    counts.update({name: 0 for name, _ in _CHECKS})
    counts.update({name: 0 for name in _TWO_PHASE_CRITERIA})
    failures: dict[str, list[str]] = {}
    hard = _hard(scenario)
    for _ in range(n):
        batch = run_scenario(scenario)
        if source_or_silence_ok(batch.trails):
            counts["source_or_silence"] += 1
        else:
            failures.setdefault("source_or_silence", ["a surfaced fact lacks source/timestamp"])
        if no_blocked_surfaced(batch.trails):
            counts["no_blocked_surfaced"] += 1
        else:
            failures.setdefault("no_blocked_surfaced", ["a blocked trail reached the feed"])
        for name, check in _CHECKS:
            violations = check(batch, hard)
            if not violations:
                counts[name] += 1
            else:
                failures.setdefault(name, violations)
        # Epic 040 D3: the same recorded bundle through BOTH paths — the split is
        # gated against the single-pass truth every run, same zero-tolerance bar.
        phase1, composed, removed = run_scenario_two_phase(scenario)
        two_phase_results: dict[str, list[str]] = {
            "phase1_silence": check_phase1_silence(phase1),
            "two_phase_composition": check_two_phase_composition(batch, phase1, composed, removed),
            "phase_order_stable": check_phase_order_stable(phase1, composed, removed),
        }
        for name, violations in two_phase_results.items():
            if not violations:
                counts[name] += 1
            else:
                failures.setdefault(name, violations)
    report = EvalReport(scenario.name, n, [CriterionResult(k, v, n) for k, v in counts.items()])
    return ScenarioResult(report=report, failures=failures)
