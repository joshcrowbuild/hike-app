#!/usr/bin/env bash
# Prune stale worktrees — the fully-merged, clean ones that are pure stale-read traps.
#
# A worktree is removed only when BOTH hold:
#   1. its branch is already merged into origin/main (nothing unmerged to lose), and
#   2. it has no uncommitted changes (nothing dirty to lose).
# The current worktree and any detached/dirty ones are always kept.
#
# Dry-run by default (prints what it WOULD remove). Pass --force to actually remove.
#   bash scripts/prune_worktrees.sh            # dry run
#   bash scripts/prune_worktrees.sh --force    # remove the safe ones
set -euo pipefail

FORCE="${1:-}"
REPO_ROOT="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | xargs dirname)"
cd "$REPO_ROOT"
git fetch origin --quiet || true

self="$(git rev-parse --show-toplevel 2>/dev/null || echo '')"
kept=0 pruned=0

# Iterate worktree paths (skip the bare/common entry).
git worktree list --porcelain | awk '/^worktree /{print $2}' | while read -r wt; do
  [ -d "$wt" ] || continue
  if [ "$wt" = "$self" ]; then
    echo "keep   $wt   (current worktree)"; kept=$((kept+1)); continue
  fi
  branch="$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null || echo HEAD)"
  dirty="$(git -C "$wt" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$dirty" != "0" ]; then
    echo "keep   $wt   ($branch — $dirty uncommitted change(s))"; kept=$((kept+1)); continue
  fi
  if [ "$branch" = "HEAD" ]; then
    echo "keep   $wt   (detached HEAD — inspect manually)"; kept=$((kept+1)); continue
  fi
  if git merge-base --is-ancestor "$wt"@ origin/main 2>/dev/null; then
    if [ "$FORCE" = "--force" ]; then
      git worktree remove --force "$wt" && echo "PRUNED $wt   ($branch — merged, clean)"
    else
      echo "would-prune $wt   ($branch — merged into main, clean)"
    fi
    pruned=$((pruned+1))
  else
    echo "keep   $wt   ($branch — has unmerged commits)"; kept=$((kept+1))
  fi
done

echo
if [ "$FORCE" != "--force" ]; then
  echo "dry run — re-run with --force to remove the 'would-prune' worktrees."
fi
