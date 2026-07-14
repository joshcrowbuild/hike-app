"""Test the owned-read lint for Rule #4 enforcement.

Verifies that:
  1. The lint catches unscoped reads on OWNED labels
  2. The lint passes reads scoped with owner_id = $viewer_id
  3. The lint passes reads scoped with owner_id IN $granted_ids
  4. The lint passes reads with # noqa: owned-read escape hatch
  5. The lint passes world-only reads (no OWNED labels)
  6. The actual three call sites (context_assembly, outcome) are properly scoped
"""

from __future__ import annotations

import sys
from pathlib import Path

# Import the lint checker directly so we can unit-test the core logic.
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from lint_owned_reads import check_cypher_string


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
