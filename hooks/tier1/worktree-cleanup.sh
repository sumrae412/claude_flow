#!/usr/bin/env bash
# Trigger: SessionStart
# Lists git worktrees and removes prunable/stale ones, in three passes:
#   1. Worktrees git still knows about whose path is gone — `worktree remove`.
#   2. .claude/worktrees/ tracking directories whose `path` file points at a
#      target that no longer exists — `rm -rf`.
#   3. Orphan worktree directories under .claude/worktrees/ that git no longer
#      registers AND have a broken .git pointer AND mtime >5 days. These
#      accumulate when `git worktree remove` is bypassed (session crash etc.)
#      and Section 1 alone cannot reach them.
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

# 3. Detect orphan worktree directories: full worktree dirs in .claude/worktrees/
#    that git no longer registers AND whose .git pointer is broken AND mtime >5 days.
#    These accumulate when `git worktree remove` was bypassed (e.g. -f rm of the
#    parent during a session crash) but the on-disk dir survives. Section 1 only
#    handles paths git still knows about; this closes that gap.
ORPHAN_AGE_DAYS=5
if [[ -d "$WORKTREE_TRACKING" ]]; then
  REGISTERED=$(git -C "$PROJECT_DIR" worktree list --porcelain 2>/dev/null \
    | grep -E '^worktree ' | awk '{print $2}')
  while IFS= read -r -d '' dir; do
    # Skip if dir IS a registered worktree path
    if printf '%s\n' "$REGISTERED" | grep -qxF "$dir"; then continue; fi
    # Heuristic: looks like a worktree (has a .git file or .git dir)
    [[ -e "$dir/.git" ]] || continue
    # Verify the .git pointer is broken — git rev-parse must fail
    if git -C "$dir" rev-parse --git-dir &>/dev/null; then continue; fi
    # Check mtime is older than ORPHAN_AGE_DAYS (find -mtime +N matches files
    # modified more than N*24h ago).
    if find "$dir" -maxdepth 0 -mtime "+${ORPHAN_AGE_DAYS}" 2>/dev/null | grep -q .; then
      echo "[worktree-cleanup] Removing orphan worktree dir (>${ORPHAN_AGE_DAYS}d, broken .git): $dir"
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
