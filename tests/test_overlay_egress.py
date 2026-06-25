"""Epic 014 S1/S2 — the private overlay never egresses to a cloud judge.

The one pipeline that carries private-overlay data is the personalized taste-ranking
call (Epic 003: assembled context → `rank_plan` → `rank_ids` as `profile=`). These
tests assert that call is structurally forced on-device whenever overlay is in play,
even when the judgment tier is the cloud yardstick (`ADVENTURE_PROVIDER_JUDGMENT=
anthropic`) — and that the anonymous / no-overlay path still resolves per config.

Fakes only; no network, no SDK, no DB. `rank_ids` is monkeypatched (AC-1.2) or a spy
provider is injected (AC-1.4/2.x) so no provider `.complete()` ever fires.
"""

from __future__ import annotations

from typing import Any

import orchestration.engine as engine_mod
from graph.client import GraphClient
from orchestration.config import Settings
from orchestration.engine import Runtime, build_runtime, plan
from orchestration.providers.anthropic_claude import AnthropicProvider
from orchestration.providers.base import LLMResponse
from orchestration.providers.local_openai import LocalOpenAIProvider
from orchestration.providers.registry import resolve

# Judgment tier pointed at the cloud yardstick — the configuration that egresses today.
ANTHROPIC_JUDGE_ENV = {
    "ADVENTURE_PROVIDER_JUDGMENT": "anthropic",
    "ADVENTURE_MODEL_JUDGMENT": "claude-yardstick",
    "ADVENTURE_LOCAL_MODEL_JUDGMENT": "local-llama",
    "ADVENTURE_PROVIDER_MECHANICAL": "local",
    "ADVENTURE_MODEL_MECHANICAL": "local-llama",
    "ANTHROPIC_API_KEY": "sk-test",
}


def _belief_row() -> dict[str, Any]:
    """A stated preference belief that survives the decay/floor filter → non-empty
    personal context (assemble_context emits 'Stated preferences: likes views.')."""
    return {
        "key": "likes_views",
        "value": True,
        "axis": "preference",
        "type": "stated",
        "confidence": 0.8,
        "corroboration_n": 5,
        "decays": False,
        "decay_half_life_days": 90,
        "last_updated_at": None,
    }


def _row(cid: str, lat: float, lon: float, dist: float) -> dict[str, Any]:
    return {
        "canonical_id": cid,
        "name": cid,
        "trailhead_id": "th",
        "distance_m": dist,
        "point": {"latitude": lat, "longitude": lon},
    }


class _Session:
    """Fake ScopedSession: Belief query returns `belief_rows` (drives overlay
    presence); Profile/Episode return []; everything else returns the trail rows."""

    def __init__(self, trail_rows: list[dict], belief_rows: list[dict]) -> None:
        self.trail_rows = trail_rows
        self.belief_rows = belief_rows

    def run(self, query: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        cypher, _ = query
        if "Belief" in cypher:
            return self.belief_rows
        if "PhysicalProfile" in cypher or "Episode" in cypher:
            return []
        return self.trail_rows


class _SpyProvider:
    """Records every complete() call so a test can prove which judge a rank used."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[Any] = []

    def complete(self, request: Any) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(text="[]", model=request.model, provider=self.name)


class _MechProvider:
    """Mechanical-tier stub returning a fixed intent-parse JSON (free-text profile)."""

    name = "local"

    def __init__(self, text: str) -> None:
        self.text = text

    def complete(self, request: Any) -> LLMResponse:
        return LLMResponse(text=self.text, model=request.model, provider=self.name)


# ── AC-1.2 — the provider rank_ids actually receives is Local, never Anthropic ──


def test_s1_ac2_rank_receives_local_provider_under_anthropic(monkeypatch: Any) -> None:
    """End-to-end through build_runtime + plan with the judgment tier = anthropic and
    a non-anonymous viewer carrying overlay: the provider handed to rank_ids is the
    LocalOpenAIProvider. FAILS before the fix (overlay routed to the cloud judge)."""
    captured: dict[str, Any] = {}

    def fake_rank_ids(items, provider, model, *, profile=None, hints=None):  # type: ignore[no-untyped-def]
        captured["provider"] = provider
        captured["profile"] = profile
        return [cid for cid, _ in items]

    monkeypatch.setattr(engine_mod, "rank_ids", fake_rank_ids)

    s = Settings.from_env(ANTHROPIC_JUDGE_ENV)
    rt = build_runtime(s, GraphClient("bolt://x", "u", "p"), "mem:josh")
    rt.session = _Session([_row("a", 38.5, -78.4, 100.0)], [_belief_row()])  # type: ignore[assignment]
    rt.probes = {}  # no live probes (build_probes would add the keyless USGS probe)
    rt.mechanical = None  # skip intent parse (real local provider would need the openai SDK)

    plan("mellow with good views", (38.5, -78.4), rt, viewer_id="mem:josh")

    assert isinstance(captured["provider"], LocalOpenAIProvider)
    assert not isinstance(captured["provider"], AnthropicProvider)
    # the overlay actually rode in the profile sent to that local judge
    assert "PERSONAL CONTEXT" in (captured["profile"] or "")


# ── AC-1.3 — the call-site resolution carries the privacy flag (regression guard) ──


def test_s1_ac3_build_runtime_resolves_overlay_judge_local_forced() -> None:
    """build_runtime resolves the overlay-carrying judge local-forced even under the
    cloud tier; the plain (anonymous-path) judge may be the cloud yardstick. FAILS if
    a future change drops touches_private_overlay= at this call site."""
    s = Settings.from_env(ANTHROPIC_JUDGE_ENV)
    rt = build_runtime(s, GraphClient("bolt://x", "u", "p"), "mem:josh")

    assert rt.personalized_judge is not None
    assert isinstance(rt.personalized_judge[0], LocalOpenAIProvider)
    assert rt.judge is not None
    assert isinstance(rt.judge[0], AnthropicProvider)

    # The deterministic resolution check the guard rests on.
    private = resolve("curate", s, touches_private_overlay=True)
    assert private.forced_local is True
    assert private.provider_name == "local"


# ── AC-1.4 — anonymous / no-overlay path is unchanged (cloud allowed) ──


def test_s1_ac4_anonymous_no_overlay_uses_config_judge() -> None:
    cloud = _SpyProvider("anthropic")
    local = _SpyProvider("local")
    rt = Runtime(
        session=_Session([_row("a", 38.5, -78.4, 100.0)], []),  # type: ignore[arg-type]
        probes={},
        judge=(cloud, "claude"),  # type: ignore[arg-type]
        personalized_judge=(local, "local-llama"),  # type: ignore[arg-type]
    )
    plan("mellow views", (38.5, -78.4), rt, viewer_id="anonymous")
    assert cloud.calls, "anonymous / no-overlay must use the configured (cloud-allowed) judge"
    assert not local.calls


def test_s1_ac4_intent_profile_only_reaches_cloud_judge() -> None:
    """An intent.profile-only (free-text) anonymous request still reaches rank_ids and
    is NOT local-forced — free text is not overlay substrate (AC-1.4 note)."""
    cloud = _SpyProvider("anthropic")
    local = _SpyProvider("local")
    rt = Runtime(
        session=_Session([_row("a", 38.5, -78.4, 100.0)], []),  # type: ignore[arg-type]
        probes={},
        mechanical=(_MechProvider('{"profile": "loves waterfalls"}'), "m"),  # type: ignore[arg-type]
        judge=(cloud, "claude"),  # type: ignore[arg-type]
        personalized_judge=(local, "local-llama"),  # type: ignore[arg-type]
    )
    plan("waterfalls", (38.5, -78.4), rt, viewer_id="anonymous")
    assert cloud.calls and not local.calls
    assert "loves waterfalls" in cloud.calls[0].messages[0]["content"]


# ── AC-2.1 — overlay never reaches the cloud judge (the structural guarantee) ──


def test_s2_ac1_overlay_never_reaches_cloud_judge() -> None:
    cloud = _SpyProvider("anthropic")
    local = _SpyProvider("local")
    rt = Runtime(
        session=_Session([_row("a", 38.5, -78.4, 100.0)], [_belief_row()]),  # type: ignore[arg-type]
        probes={},
        judge=(cloud, "claude"),  # type: ignore[arg-type]
        personalized_judge=(local, "local-llama"),  # type: ignore[arg-type]
    )
    plan("mellow views", (38.5, -78.4), rt, viewer_id="mem:josh")
    assert local.calls, "overlay-carrying rank must use the local-forced judge"
    assert not cloud.calls, "overlay must never reach the cloud judge"
    assert "PERSONAL CONTEXT" in local.calls[0].messages[0]["content"]


# ── AC-2.3 — the eval `judge` role and the mechanical tier are left unchanged ──


def test_s2_ac3_judge_role_and_mechanical_not_over_forced_local() -> None:
    """Only the overlay-carrying `curate` call is privacy-routed. The `judge` (eval)
    role shares the judgment tier but carries no overlay; the mechanical `extract`
    tier is intent free-text — neither is forced local (Rule #2 cloud yardstick)."""
    s = Settings.from_env(ANTHROPIC_JUDGE_ENV)
    assert resolve("judge", s).forced_local is False
    assert resolve("judge", s).provider_name == "anthropic"
    assert resolve("extract", s).forced_local is False


# ── AC-2.1 (broadening) — a non-anonymous viewer routes local even with empty overlay ──


def test_s2_ac1_non_anonymous_empty_overlay_uses_local_judge() -> None:
    """Deliberate, privacy-conservative broadening of AC-1.4's overlay-only trigger:
    an authenticated (non-anonymous) viewer keeps ranking on-device even when this
    run's overlay happens to be empty — defense-in-depth, never a leak."""
    cloud = _SpyProvider("anthropic")
    local = _SpyProvider("local")
    rt = Runtime(
        session=_Session(
            [_row("a", 38.5, -78.4, 100.0)], []
        ),  # empty overlay  # type: ignore[arg-type]
        probes={},
        judge=(cloud, "claude"),  # type: ignore[arg-type]
        personalized_judge=(local, "local-llama"),  # type: ignore[arg-type]
    )
    plan("mellow views", (38.5, -78.4), rt, viewer_id="mem:josh")
    assert local.calls, "an authenticated viewer ranks on-device even with empty overlay"
    assert not cloud.calls


# ── AC-2.4 / AC-3.6 — the privacy-routing + auth-precondition contract is pinned ──


def test_s2_ac4_and_ac3_6_build_runtime_docstring_pins_contract() -> None:
    doc = build_runtime.__doc__ or ""
    # AC-2.4 — the taste-ranking resolution is documented as privacy-routed.
    assert "privacy-routed" in doc
    assert "personal-overlay" in doc
    # AC-3.6 — the "viewer_id is already authenticated" precondition is documented.
    assert "already authenticated" in doc
