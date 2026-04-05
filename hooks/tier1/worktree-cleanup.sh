#!/usr/bin/env bash
# Trigger: SessionStart
# Lists git worktrees and removes prunable/stale ones.
# A worktree is considered prunable if:
#   - git worktree list reports it as "prunable", OR
#   - its path no longer exists on disk
# Also checks $CLAUDE_PROJECT_DIR/.claude/worktrees/ for stale directory entries.
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

if ! git -C "$PROJECT_DIR" rev-parse --git-dir &>/dev/null; then
  exit 0
fi

CLEANED=0

# 1. Prune locked/stale worktrees reported by git
PRUNABLE=$(git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null \
  | grep -E '^worktree ' \
  | awk '{print $2}' \
  | while read -r wt_path; do
      if [[ "$wt_path" != "$PROJECT_DIR" ]] && [[ ! -d "$wt_path" ]]; then
        echo "$wt_path"
      fi
    done || true)

if [[ -n "$PRUNABLE" ]]; then
  echo "[worktree-cleanup] Pruning stale worktrees:"
  while IFS= read -r wt; do
    echo "  - $wt"
    git -C "$PROJECT_DIR" worktree remove --force "$wt" 2>/dev/null || \
      git -C "$PROJECT_DIR" worktree prune 2>/dev/null || true
    (( CLEANED++ )) || true
  done <<< "$PRUNABLE"
fi

# Run git worktree prune once to handle any remaining locks
git -C "$PROJECT_DIR" worktree prune 2>/dev/null || true

# 2. Check .claude/worktrees/ for stale tracking directories
WORKTREE_TRACKING="$PROJECT_DIR/.claude/worktrees"
if [[ -d "$WORKTREE_TRACKING" ]]; then
  while IFS= read -r -d '' dir; do
    # If the directory name corresponds to a path that no longer exists as a worktree
    TARGET=$(cat "$dir/path" 2>/dev/null || echo "")
    if [[ -n "$TARGET" ]] && [[ ! -d "$TARGET" ]]; then
      echo "[worktree-cleanup] Removing stale tracking dir: $dir (target: $TARGET)"
      rm -rf "$dir"
      (( CLEANED++ )) || true
    fi
  done < <(find "$WORKTREE_TRACKING" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null || true)
fi

if [[ "$CLEANED" -eq 0 ]]; then
  echo "[worktree-cleanup] No stale worktrees found."
else
  echo "[worktree-cleanup] Cleaned $CLEANED stale worktree entry/entries."
fi

exit 0
