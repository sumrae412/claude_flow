#!/usr/bin/env bash
#
# Deterministic claude_flow repo audit for the weekly scheduled cleanup task.
#
# Emits one JSON object to stdout. The scheduled task uses `has_delta` to
# decide whether a full report is needed or a one-line "no change" suffices.
#
# Humans can also run this directly:
#     ./scripts/cleanup-audit.sh             # default: 7-day lookback
#     ./scripts/cleanup-audit.sh --since=2026-05-15
#
# Design notes:
# - All checks are deterministic — no LLM, no network beyond `gh pr list`.
#   Maps to CLAUDE.md pipeline-discipline Rule 5 (model only for judgment).
# - Exit 0 always; errors surface as fields, not exit codes.

set -uo pipefail

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || { echo '{"error":"not_a_git_repo"}'; exit 0; }
cd "$ROOT"

# --- argument parsing ------------------------------------------------------
SINCE=""
for arg in "$@"; do
  case "$arg" in
    --since=*) SINCE="${arg#--since=}" ;;
  esac
done
if [ -z "$SINCE" ]; then
  SINCE=$(date -v-7d +%Y-%m-%d 2>/dev/null || date -d "7 days ago" +%Y-%m-%d 2>/dev/null || echo "1970-01-01")
fi

# --- git delta -------------------------------------------------------------
COMMITS_SINCE=$(git log --since="$SINCE" --oneline 2>/dev/null | wc -l | tr -d ' ')
HEAD_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "")
AHEAD_BEHIND=$(git rev-list --left-right --count HEAD...origin/main 2>/dev/null || printf "0\t0")
AHEAD=$(printf '%s' "$AHEAD_BEHIND" | cut -f1)
BEHIND=$(printf '%s' "$AHEAD_BEHIND" | cut -f2)

# --- open PRs --------------------------------------------------------------
if command -v gh >/dev/null 2>&1; then
  OPEN_PRS=$(gh pr list --state open --json number 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d))' 2>/dev/null || echo "-1")
else
  OPEN_PRS="-1"
fi

# --- worktrees -------------------------------------------------------------
STALE_DAYS=5
NOW_TS=$(date +%s)
STALE_WORKTREES=()
DIRTY_WORKTREES=()
WORKTREE_COUNT=0
if [ -d .claude/worktrees ]; then
  for wt in .claude/worktrees/*/; do
    [ -d "$wt" ] || continue
    WORKTREE_COUNT=$((WORKTREE_COUNT + 1))
    MTIME=$(stat -f %m "$wt" 2>/dev/null || stat -c %Y "$wt" 2>/dev/null || echo "$NOW_TS")
    AGE_DAYS=$(( (NOW_TS - MTIME) / 86400 ))
    if [ "$AGE_DAYS" -gt "$STALE_DAYS" ]; then
      STALE_WORKTREES+=("${wt} (${AGE_DAYS}d)")
    fi
    DIRTY=$(git -C "$wt" status --short 2>/dev/null | wc -l | tr -d ' ')
    if [ "$DIRTY" -gt 0 ]; then
      DIRTY_WORKTREES+=("${wt} (${DIRTY} file changes)")
    fi
  done
fi

# --- hook counts -----------------------------------------------------------
HOOK_COUNTS=$(python3 -c '
import json
try:
    d = json.load(open("hooks/hook-registry.json"))
    hs = d.get("hooks", [])
    t1 = sum(1 for h in hs if h.get("tier") == 1)
    t2 = sum(1 for h in hs if h.get("tier") == 2)
    print(f"{t1},{t2}")
except Exception:
    print("-1,-1")
' 2>/dev/null)
TIER1_REG=$(echo "$HOOK_COUNTS" | cut -d, -f1)
TIER2_REG=$(echo "$HOOK_COUNTS" | cut -d, -f2)
TIER1_README=$(grep -oE "[0-9]+ universal hooks" README.md 2>/dev/null | head -1 | grep -oE "[0-9]+" || echo "")
TIER2_README=$(grep -oE "[0-9]+ stack-specific hooks" README.md 2>/dev/null | head -1 | grep -oE "[0-9]+" || echo "")
README_DRIFT="false"
[ "$TIER1_REG" != "$TIER1_README" ] && README_DRIFT="true"
[ "$TIER2_REG" != "$TIER2_README" ] && README_DRIFT="true"

# --- stray markers ---------------------------------------------------------
MARKERS=$(grep -rn --include="*.py" --include="*.ts" --include="*.js" \
  -E "(FIXME|XXX|HACK)" \
  --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=.git \
  --exclude-dir=__pycache__ --exclude-dir=.pytest_cache --exclude-dir=.claude \
  . 2>/dev/null | wc -l | tr -d ' ')

TODOS_NON_PRICING=$(grep -rn --include="*.py" --include="*.ts" --include="*.js" \
  -E "TODO" \
  --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=.git \
  --exclude-dir=__pycache__ --exclude-dir=.pytest_cache --exclude-dir=.claude \
  . 2>/dev/null | grep -v "scripts/pricing.py" | wc -l | tr -d ' ')

LAST_REPORT=$(ls -1 docs/cleanup-report-*.md 2>/dev/null | sort | tail -1)

# --- emit JSON (let Python decide booleans / delta) ------------------------
export SINCE HEAD_SHA AHEAD BEHIND COMMITS_SINCE OPEN_PRS WORKTREE_COUNT
export TIER1_REG TIER2_REG TIER1_README TIER2_README README_DRIFT
export MARKERS TODOS_NON_PRICING LAST_REPORT
STALE_JSON=$(printf '%s\n' "${STALE_WORKTREES[@]:-}" | python3 -c 'import json,sys; print(json.dumps([l for l in sys.stdin.read().splitlines() if l.strip()]))')
DIRTY_JSON=$(printf '%s\n' "${DIRTY_WORKTREES[@]:-}" | python3 -c 'import json,sys; print(json.dumps([l for l in sys.stdin.read().splitlines() if l.strip()]))')
export STALE_JSON DIRTY_JSON

python3 <<'EOF'
import json, os

def i(name, default=0):
    v = os.environ.get(name, "").strip()
    try: return int(v)
    except: return default

out = {
  "since": os.environ.get("SINCE", ""),
  "head": os.environ.get("HEAD_SHA", ""),
  "ahead_of_origin": i("AHEAD"),
  "behind_origin": i("BEHIND"),
  "commits_since": i("COMMITS_SINCE"),
  "open_prs": i("OPEN_PRS", -1),
  "worktrees": {
    "total": i("WORKTREE_COUNT"),
    "stale": json.loads(os.environ.get("STALE_JSON", "[]")),
    "dirty": json.loads(os.environ.get("DIRTY_JSON", "[]")),
  },
  "hooks": {
    "tier1_registry": i("TIER1_REG", -1),
    "tier2_registry": i("TIER2_REG", -1),
    "tier1_readme": os.environ.get("TIER1_README", ""),
    "tier2_readme": os.environ.get("TIER2_README", ""),
    "readme_drift": os.environ.get("README_DRIFT", "false") == "true",
  },
  "stray_markers": {
    "fixme_xxx_hack": i("MARKERS"),
    "todos_non_pricing": i("TODOS_NON_PRICING"),
  },
  "last_report": os.environ.get("LAST_REPORT", ""),
}

has_delta = (
    out["commits_since"] > 0
    or (out["open_prs"] is not None and out["open_prs"] > 0)
    or len(out["worktrees"]["stale"]) > 0
    or len(out["worktrees"]["dirty"]) > 0
    or out["hooks"]["readme_drift"]
    or out["stray_markers"]["fixme_xxx_hack"] > 0
)
out["has_delta"] = has_delta

print(json.dumps(out, indent=2))
EOF
