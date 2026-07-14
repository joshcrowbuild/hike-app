"""Test the owned-read lint for Rule #4 enforcement.

Verifies that:
  1. The lint catches unscoped reads on OWNED labels
  2. The lint passes reads scoped with owner_id = $viewer_id
  3. The lint passes reads scoped with owner_id IN $granted_ids
  4. The lint passes reads with # noqa: owned-read escape hatch
  5. The lint passes world-only reads (no OWNED labels)
  6. The actual three call sites (context_assembly, outcome) are properly scoped
  7. (M10) The lint is JOIN-AWARE: a multi-fragment Cypher assembly (the shape every
     `graph.queries` builder uses — a tuple of sibling string literals concatenated
     into one statement) is scope-checked as the WHOLE assembled query, not each
     physical fragment in isolation. A fragment-blind lint sees the owned `MATCH`
     fragment alone (no scope token in THAT fragment) and either false-positives —
     forcing a blanket `# noqa` that a genuinely unscoped read could hide behind —
     or, checked the other way, simply never notices the scope clause living in a
     sibling fragment. These fixtures prove both directions on the ACTUAL assembly
     shape (an `ast.parse`d module, not a hand-joined string), using
     `find_cypher_groups` + `check_cypher_group` — the join-aware entry points.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Import the lint checker directly so we can unit-test the core logic.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from lint_owned_reads import check_cypher_group, check_cypher_string, find_cypher_groups


class TestOwnedReadLint:
    """Test the owned-read lint checker."""

    def test_catch_unscoped_belief_read(self) -> None:
        """Unscoped read on :Belief should fail."""
        cypher = "MATCH (b:Belief) RETURN b.key, b.value"
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is not None
        assert "unscoped read" in error
        assert "Belief" in error

    def test_catch_unscoped_outcome_read(self) -> None:
        """Unscoped read on :Outcome should fail."""
        cypher = "MATCH (o:Outcome) WHERE o.episode_id = $eid RETURN o.overall"
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is not None
        assert "unscoped read" in error
        assert "Outcome" in error

    def test_catch_unscoped_physical_profile_read(self) -> None:
        """Unscoped read on :PhysicalProfile should fail."""
        cypher = "MATCH (pp:PhysicalProfile) RETURN pp.pace_on_grade"
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is not None
        assert "unscoped read" in error
        assert "PhysicalProfile" in error

    def test_catch_unscoped_episode_read(self) -> None:
        """Unscoped read on :Episode should fail."""
        cypher = "MATCH (e:Episode) RETURN e.date"
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is not None
        assert "unscoped read" in error

    def test_pass_scoped_with_viewer_id(self) -> None:
        """Scoped read with owner_id = $viewer_id should pass."""
        cypher = "MATCH (b:Belief) WHERE b.owner_id = $viewer_id RETURN b.key"
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is None

    def test_pass_scoped_with_granted_ids(self) -> None:
        """Scoped read with owner_id IN $granted_ids should pass."""
        cypher = "MATCH (e:Episode) WHERE e.owner_id IN $granted_ids RETURN e.date"
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is None

    def test_pass_with_owner_scope_function(self) -> None:
        """Scoped read using owner_scope() helper should pass."""
        cypher = "MATCH (b:Belief) WHERE owner_scope(b) RETURN b.key"
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is None

    def test_pass_noqa_escape_hatch_same_line(self) -> None:
        """Unscoped read with # noqa: owned-read on same line should pass."""
        cypher = "MATCH (b:Belief) RETURN b.key  # noqa: owned-read debug query"
        source_lines = [cypher]
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=source_lines)
        assert error is None

    def test_pass_noqa_escape_hatch_previous_line(self) -> None:
        """Unscoped read with # noqa on line before should pass."""
        cypher = "MATCH (b:Belief) RETURN b.key"
        source_lines = ["# noqa: owned-read owner-scoped belief recount", cypher]
        error = check_cypher_string(cypher, line=2, filename="test.py", source_lines=source_lines)
        assert error is None

    def test_pass_world_only_read(self) -> None:
        """Read on world-only labels should pass (no OWNED labels)."""
        cypher = "MATCH (t:CanonicalTrail) RETURN t.name"
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is None

    def test_pass_world_trailhead_read(self) -> None:
        """Read on :Trailhead should pass (world label)."""
        cypher = "MATCH (h:Trailhead) RETURN h.name"
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is None

    def test_fixture_context_assembly_fetch_beliefs(self) -> None:
        """The actual fetch_beliefs query from context_assembly.py should pass."""
        # This is the actual Cypher from orchestration/context_assembly.py:69-79
        cypher = (
            "MATCH (b:Belief) "
            "WHERE b.owner_id = $viewer_id "
            "RETURN b.key AS key, b.value AS value, b.axis AS axis, b.type AS type, "
            "       b.confidence AS confidence, b.corroboration_n AS corroboration_n, "
            "       b.decays AS decays, b.decay_half_life_days AS decay_half_life_days, "
            "       b.last_updated_at AS last_updated_at "
            "ORDER BY b.last_updated_at DESC "
            "LIMIT $limit"
        )
        error = check_cypher_string(
            cypher, line=70, filename="orchestration/context_assembly.py", source_lines=[]
        )
        assert error is None

    def test_fixture_context_assembly_fetch_profile(self) -> None:
        """The actual fetch_profile query from context_assembly.py should pass."""
        # This is the actual Cypher from orchestration/context_assembly.py:95-101
        cypher = (
            "MATCH (pp:PhysicalProfile) "
            "WHERE pp.owner_id = $viewer_id "
            "RETURN pp.pace_on_grade AS pace_on_grade, "
            "       pp.max_distance_m AS max_distance_m, "
            "       pp.max_ascent_m AS max_ascent_m, "
            "       pp.episode_count AS episode_count"
        )
        error = check_cypher_string(
            cypher, line=95, filename="orchestration/context_assembly.py", source_lines=[]
        )
        assert error is None

    def test_fixture_context_assembly_fetch_episodes(self) -> None:
        """The actual fetch_relevant_episodes query from context_assembly.py should pass."""
        # This is the actual Cypher from orchestration/context_assembly.py:128-136
        cypher = (
            "MATCH (p:Person {member_id: $viewer_id})-[:DID]->(e:Episode)"
            "-[:ON]->(t:CanonicalTrail) "
            "WHERE e.owner_id = $viewer_id "
            "  AND t.canonical_id IN $candidate_ids "
            "  AND e.date >= $cutoff "
            "RETURN t.name AS trail_name, e.date AS date, e.overall_outcome AS overall "
            "ORDER BY e.date DESC "
            "LIMIT $limit"
        )
        error = check_cypher_string(
            cypher, line=129, filename="orchestration/context_assembly.py", source_lines=[]
        )
        assert error is None

    def test_fixture_outcome_write_episode_check(self) -> None:
        """The episode ownership check from outcome.py should pass."""
        # This is the actual Cypher from orchestration/outcome.py:89-91
        cypher = (
            "MATCH (e:Episode {episode_id: $eid})\n"
            "WHERE e.owner_id = $viewer_id\n"
            "RETURN e.episode_id AS episode_id"
        )
        error = check_cypher_string(
            cypher, line=89, filename="orchestration/outcome.py", source_lines=[]
        )
        assert error is None

    def test_error_includes_filename_and_line(self) -> None:
        """Error messages should include filename and line number."""
        cypher = "MATCH (b:Belief) RETURN b.key"
        error = check_cypher_string(cypher, line=42, filename="some_file.py", source_lines=[])
        assert error is not None
        assert "some_file.py:42" in error

    def test_case_insensitive_label_matching(self) -> None:
        """Label matching should be case-insensitive (Cypher allows it)."""
        cypher = "MATCH (b:belief) RETURN b.key"  # lowercase 'belief'
        error = check_cypher_string(cypher, line=1, filename="test.py", source_lines=[])
        assert error is not None
        assert "unscoped read" in error


class TestIntegrationWithActualFiles:
    """Integration tests against the actual codebase files."""

    def test_context_assembly_file_passes(self) -> None:
        """The full context_assembly.py file should pass the lint."""
        from scripts import lint_owned_reads

        path = Path(__file__).parent.parent / "orchestration" / "context_assembly.py"
        errors = lint_owned_reads.scan_file(path)
        assert errors == [], f"context_assembly.py has unscoped reads: {errors}"

    def test_outcome_file_passes(self) -> None:
        """The full outcome.py file should pass the lint."""
        from scripts import lint_owned_reads

        path = Path(__file__).parent.parent / "orchestration" / "outcome.py"
        errors = lint_owned_reads.scan_file(path)
        assert errors == [], f"outcome.py has unscoped reads: {errors}"

    def test_graph_queries_file_passes_with_no_noqa_markers(self) -> None:
        """graph/queries.py — the module every owned builder lives in — passes the
        JOIN-AWARE lint with ZERO functional lint-escape markers anywhere in the file
        (M10). Before the join-aware fix, 11 builders needed a blanket escape comment
        because the lint checked the owned `MATCH`/`MERGE` fragment in isolation from
        its `WHERE owner_scope(...)` (or `{owner_id: $viewer_id}`) sibling fragment.
        This is the acceptance bar for M10: the reads pass BY CONSTRUCTION, not by an
        escape hatch that could silently paper over a genuinely unscoped read.

        Checks the lint's own noqa-detection regex line-by-line (not a bare substring
        check) so this doesn't false-positive on module docstring prose that merely
        *talks about* the escape marker without using it live."""
        from scripts import lint_owned_reads

        path = Path(__file__).parent.parent / "graph" / "queries.py"
        source = path.read_text(encoding="utf-8")
        live_markers = [
            (i, line)
            for i, line in enumerate(source.split("\n"), start=1)
            if lint_owned_reads._NOQA_RE.search(line)
        ]
        assert live_markers == [], (
            f"graph/queries.py should carry no lint-escape markers now the lint is "
            f"join-aware: {live_markers}"
        )
        errors = lint_owned_reads.scan_file(path)
        assert errors == [], f"graph/queries.py has unscoped reads: {errors}"


class TestJoinAwareMultiFragmentAssembly:
    """(M10) The lint must assemble sibling string-literal fragments that concatenate
    into ONE Cypher string — implicit/adjacent concatenation, `+`, and f-string parts
    within a single assignment — BEFORE scope-checking, instead of checking each
    physical fragment on its own. Falsifiability is the point: a multi-fragment read
    scoped via a sibling `WHERE owner_scope(...)` fragment must PASS without a `#
    noqa`, and a multi-fragment read with NO scope anywhere in the assembly must
    still FAIL. Both fixtures below are parsed as real modules (`ast.parse`), not
    hand-joined strings, so they exercise the exact AST shape `graph/queries.py`
    uses.
    """

    def _groups_in(self, source: str) -> list[tuple[str, int, int]]:
        tree = ast.parse(source)
        return find_cypher_groups(tree)

    def test_multi_fragment_read_scoped_via_sibling_fragment_passes(self) -> None:
        """A tuple-of-fragments Cypher assembly — the owned `MATCH` in one string
        literal, its `WHERE owner_scope(...)` in a SEPARATE sibling f-string fragment,
        mirroring `graph.queries.episode_fields_read` — passes with NO `# noqa`. A
        fragment-blind lint would see only the first fragment (no scope token in it)
        and flag it; the join-aware lint sees the assembled whole."""
        source = (
            "def episode_fields_read(episode_id):\n"
            "    cypher = (\n"
            '        "MATCH (e:Episode {episode_id: $eid})\\n"\n'
            "        f\"WHERE {owner_scope('e')}\\n\"\n"
            '        "RETURN e.distance_m AS distance_m"\n'
            "    )\n"
            '    return cypher, {"eid": episode_id}\n'
        )
        groups = self._groups_in(source)
        assert len(groups) == 1, f"expected exactly one assembled group, got {groups}"
        text, lo, hi = groups[0]
        assert "Episode" in text and "owner_scope(" in text  # the whole join, not one fragment
        error = check_cypher_group(text, lo, hi, "fixture.py", source.split("\n"))
        assert error is None, f"expected the scoped multi-fragment read to pass, got: {error}"

    def test_multi_fragment_read_with_no_scope_anywhere_still_fails(self) -> None:
        """The falsification case: a tuple-of-fragments Cypher assembly touching TWO
        owned labels (Belief, Outcome) across separate string literals, with NO scope
        token in ANY fragment, must still be flagged — proving the join-aware fix
        doesn't just make every multi-fragment read pass by construction."""
        source = (
            "def leaky_read(belief_id, outcome_id):\n"
            "    cypher = (\n"
            '        "MATCH (b:Belief {belief_id: $bid})\\n"\n'
            '        "MATCH (o:Outcome {outcome_id: $oid})\\n"\n'
            '        "RETURN b.value AS value"\n'
            "    )\n"
            '    return cypher, {"bid": belief_id, "oid": outcome_id}\n'
        )
        groups = self._groups_in(source)
        assert len(groups) == 1, f"expected exactly one assembled group, got {groups}"
        text, lo, hi = groups[0]
        error = check_cypher_group(text, lo, hi, "fixture.py", source.split("\n"))
        assert error is not None, "expected the unscoped multi-fragment read to be flagged"
        assert "Belief" in error and "Outcome" in error

    def test_multi_fragment_write_scoped_via_map_pattern_key_passes(self) -> None:
        """The write-shaped mirror: `MERGE (e:Episode {episode_id: $eid, owner_id:
        $viewer_id})` scoped by a map-pattern key (not `owner_scope`/`WHERE`), matching
        `graph.queries.upsert_episode`, passes — the scope token lives in the SAME
        fragment here, but this pins that the broadened `owner_id: $viewer_id` match
        (no exclusive-brace requirement) still works standalone."""
        source = (
            "def upsert_episode(episode_id):\n"
            "    cypher = (\n"
            '        "MERGE (e:Episode {episode_id: $eid, owner_id: $viewer_id})\\n"\n'
            '        "ON CREATE SET e.created_at = $now"\n'
            "    )\n"
            '    return cypher, {"eid": episode_id}\n'
        )
        groups = self._groups_in(source)
        text, lo, hi = groups[0]
        error = check_cypher_group(text, lo, hi, "fixture.py", source.split("\n"))
        assert error is None, f"expected the map-pattern-scoped write to pass, got: {error}"

    def test_multi_fragment_noqa_on_opening_line_escapes_the_whole_group(self) -> None:
        """A `# noqa` on the `cypher = (` opening line (as several pre-M10 builders
        carried it, e.g. `wire_person_did_episode`) still escapes the assembled
        group — kept for any genuinely non-viewer context that still needs the
        escape hatch after the join-aware fix."""
        source = (
            "def deliberately_unscoped():\n"
            "    cypher = (  # noqa: owned-read maintenance scan\n"
            '        "MATCH (b:Belief)\\n"\n'
            '        "RETURN b.value AS value"\n'
            "    )\n"
            "    return cypher, {}\n"
        )
        groups = self._groups_in(source)
        text, lo, hi = groups[0]
        error = check_cypher_group(text, lo, hi, "fixture.py", source.split("\n"))
        assert error is None, "expected the noqa on the enclosing line to escape the group"

    def test_binop_plus_chain_to_unresolvable_name_does_not_widen_span_to_line_1(self) -> None:
        """Regression: a `cypher = "MATCH ..." + MODULE_LEVEL_CONSTANT` assembly (the
        shape `graph.queries.trail_detail`/`trails_detail` use to append the shared
        `_TRAIL_DETAIL_PROJECTION`) must resolve to the group's OWN line span — not
        widen to line 1.

        The bug this pins: `_line_span` walked the whole AST subtree taking min/max
        of every child's `lineno`, but a `BinOp`'s operator node (`ast.Add`) and a
        `Name`'s context node (`ast.Load`) carry NO `lineno` at all. An early version
        defaulted a missing `lineno` to `1` via `getattr(node, "lineno", 1)`, so the
        moment a `+`-assembly appeared, its computed span silently became `(1,
        actual_end_line)` instead of `(actual_line, actual_line)`. That's a security-
        relevant false widener: `check_cypher_group` treats a `# noqa` ANYWHERE in the
        span as escaping the group, so a group wrongly spanning line 1 through its
        real line would let an unrelated noqa comment near the top of the file
        silently suppress a real unscoped-read error anywhere below it."""
        source = (
            "_PROJECTION = 'RETURN t.name'\n"
            "\n"
            "\n"
            "def trail_detail(canonical_id):\n"
            '    cypher = "MATCH (t:CanonicalTrail {canonical_id: $cid})\\n" + _PROJECTION\n'
            '    return cypher, {"cid": canonical_id}\n'
        )
        groups = self._groups_in(source)
        assert len(groups) == 1, f"expected exactly one assembled group, got {groups}"
        _text, lo, hi = groups[0]
        assert lo == 5 and hi == 5, (
            f"expected the group's span to be its own line (5, 5), not widened toward "
            f"line 1 by the unresolvable +-chain tail; got ({lo}, {hi})"
        )
