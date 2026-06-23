"""The Phase-0 engine: Scout -> Verifier -> Curator (code-orchestrated workflow).

A fixed, authored DAG — not an autonomous agent (Stage 4 §1). Stage 0 ships the
shape; each stage is implemented in Stage 4:

    Scout    - scoped Cypher candidate generation (graph.scoped_session),
               capped to top-K.
    Verifier - JIT live calls via orchestration.adapters; source-or-silence
               enforced in code; live data never persisted (rule #3).
    Curator  - hard constraint filters (guardrails) + judgment-tier taste
               ranking that never lets confidence penalize rank (rule #2).
"""

from __future__ import annotations

from orchestration.config import Settings


def plan(query: str, viewer_id: str, settings: Settings) -> object:
    """Produce the calm, curated, verified feed for `viewer_id`. Implemented in Stage 4."""
    raise NotImplementedError("engine.plan is implemented in Stage 4")
