#!/usr/bin/env bash
#
# dispatch-epic-018.sh — fan out Epic 018 (live conditions on the card) code lanes
# as parallel, headless Claude Code agents, one git worktree per lane.
#
# Prereqs (run on YOUR machine, not CI):
#   - Claude Code CLI (`claude`) installed and logged in
#   - `gh` authenticated (`gh auth status`) for the auto-PR step
#   - The Epic 018 spec present on the base branch (merge its PR to main first,
#     or set BASE to the epic branch)
#   - Local toolchain for `make check`: Python env (S3/S5/S6) + Node/Vitest (S4);
#     the Neo4j integration leg needs a local DB or the agent will draft the PR and say so
#
# Usage:
#   ./scripts/dispatch-epic-018.sh
#   BASE=origin/claude/epic-018-live-conditions-plan ./scripts/dispatch-epic-018.sh   # before the epic is on main
#   MODEL=sonnet ./scripts/dispatch-epic-018.sh
#
# Safety: uses --dangerously-skip-permissions for unattended runs — it bypasses ALL
# permission checks (including arbitrary bash). Only run in a repo/machine you trust.
# For a guarded run, swap it for:
#   --permission-mode acceptEdits --allowedTools "Bash(git *),Bash(make *),Bash(gh *),Read,Edit,Write"
#
set -euo pipefail

REPO="$(git rev-parse --show-toplevel)"
PARENT="$(dirname "$REPO")"
SPEC="docs/epics/epic-018-live-conditions-on-the-card.md"
BASE="${BASE:-origin/main}"
MODEL="${MODEL:-opus}"
LOGDIR="$PARENT/dispatch-018-logs"
mkdir -p "$LOGDIR"

git -C "$REPO" fetch origin --quiet

# id | branch-slug | story instruction (the four buildable CODE lanes; S1/S2 are Render ops)
LANES=(
  "s3|adapter-hardening|Story S3 — live-harden and cassette-gate the live adapters so source-or-silence is proven in CI."
  "s4|frontend-silence|Story S4 — honest condition rendering plus the four silence states (CDP-02) in the frontend card."
  "s5|guardrail-conditions|Story S5 — guardrail interplay: a real hazard sets a trail aside with its source-stamped reason."
  "s6|cost-latency|Story S6 — measure and bound cost/latency on the live fan-out and tune per-source TTLs."
)

pids=()
for lane in "${LANES[@]}"; do
  IFS='|' read -r id slug story <<< "$lane"
  branch="claude/018-$id-$slug"
  wt="$PARENT/hike-018-$id"

  echo "▶ $id → $wt ($branch)"
  git -C "$REPO" worktree add -B "$branch" "$wt" "$BASE" >/dev/null

  if [ ! -f "$wt/$SPEC" ]; then
    echo "  ✗ $SPEC not on $BASE — merge the Epic 018 PR to main, or set BASE to the epic branch."
    git -C "$REPO" worktree remove --force "$wt"
    continue
  fi

  read -r -d '' prompt <<EOF || true
You are implementing ONE lane of a build epic. Read $SPEC in full, then implement:
$story
Honor that story's Acceptance Criteria exactly and touch only its files. If you change the
API/wire contract, add or update the frozen contract test (mirror tests/test_maps_contract.py).
When finished: run 'make check' until it is green; make one logical commit (imperative
<=72-char subject + a why body + the Co-Authored-By trailer per AGENTS.md); push -u origin
$branch; then open a PR with: gh pr create --fill --base main
If 'make check' cannot be made green, stop and open the PR as a DRAFT explaining what is blocked.
EOF

  ( cd "$wt" && claude -p "$prompt" \
       --model "$MODEL" \
       --dangerously-skip-permissions \
       --output-format json > "$LOGDIR/$id.json" 2>&1 ) &
  pids+=("$!")
done

echo "⏳ ${#pids[@]} agents building in parallel… logs: $LOGDIR"
wait
echo "✅ done."
echo "   review:  gh pr list"
echo "   logs:    $LOGDIR/*.json"
echo "   cleanup: git worktree remove $PARENT/hike-018-s3   (repeat per lane)"
