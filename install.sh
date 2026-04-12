#!/usr/bin/env bash
set -euo pipefail

# Claude Flow — Code Creation Workflow installer
# Copies all skills, scripts, and hooks to ~/.claude/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_HOME:-$HOME/.claude}"
SKILLS_DIR="$CLAUDE_DIR/skills"
SCRIPTS_DIR="$CLAUDE_DIR/scripts"
HOOKS_DIR="$CLAUDE_DIR/hooks/claude-flow"

# Colors (if terminal supports them)
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  CYAN='\033[0;36m'
  NC='\033[0m'
else
  GREEN='' YELLOW='' BLUE='' CYAN='' NC=''
fi

# ─── --generate-hooks mode ──────────────────────────────────────────────────

if [[ "${1:-}" == "--generate-hooks" ]]; then
  REGISTRY="$HOOKS_DIR/hook-registry.json"
  if [ ! -f "$REGISTRY" ]; then
    echo "Error: hook-registry.json not found at $REGISTRY" >&2
    echo "Run ./install.sh first to install hooks." >&2
    exit 1
  fi

  PROJECT_DIR="${PWD}"
  echo -e "${BLUE}Detecting stack tags in: $PROJECT_DIR${NC}"
  echo ""

  # Detect stack tags
  TAGS=()

  # python
  if [ -f "$PROJECT_DIR/pyproject.toml" ]; then
    TAGS+=("python")

    # ruff
    if python3 -c "
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib
with open('$PROJECT_DIR/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
sys.exit(0 if 'ruff' in data.get('tool', {}) else 1)
" 2>/dev/null; then
      TAGS+=("ruff")
    fi

    # pytest
    if python3 -c "
import sys
try:
    import tomllib
except ImportError:
    import tomli as tomllib
with open('$PROJECT_DIR/pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
cfg = data.get('tool', {})
sys.exit(0 if 'pytest' in cfg or 'pytest-ini-options' in cfg else 1)
" 2>/dev/null || [ -f "$PROJECT_DIR/conftest.py" ]; then
      TAGS+=("pytest")
    fi
  fi

  # flake8
  if [ -f "$PROJECT_DIR/.flake8" ]; then
    TAGS+=("flake8")
  elif [ -f "$PROJECT_DIR/setup.cfg" ] && python3 -c "
import configparser, sys
c = configparser.ConfigParser()
c.read('$PROJECT_DIR/setup.cfg')
sys.exit(0 if 'flake8' in c else 1)
" 2>/dev/null; then
    TAGS+=("flake8")
  fi

  # node
  if [ -f "$PROJECT_DIR/package.json" ]; then
    TAGS+=("node")

    # eslint
    if python3 -c "
import json, sys
with open('$PROJECT_DIR/package.json') as f:
    pkg = json.load(f)
deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
sys.exit(0 if any('eslint' in k for k in deps) else 1)
" 2>/dev/null; then
      TAGS+=("eslint")
    fi

    # jest
    if python3 -c "
import json, sys
with open('$PROJECT_DIR/package.json') as f:
    pkg = json.load(f)
deps = {**pkg.get('dependencies', {}), **pkg.get('devDependencies', {})}
sys.exit(0 if 'jest' in deps else 1)
" 2>/dev/null; then
      TAGS+=("jest")
    fi
  fi

  # typescript
  if [ -f "$PROJECT_DIR/tsconfig.json" ]; then
    TAGS+=("typescript")
  fi

  # alembic
  if [ -d "$PROJECT_DIR/alembic" ] || [ -f "$PROJECT_DIR/alembic.ini" ]; then
    TAGS+=("alembic")
  fi

  # docker
  if [ -f "$PROJECT_DIR/Dockerfile" ] || [ -f "$PROJECT_DIR/docker-compose.yml" ] || [ -f "$PROJECT_DIR/docker-compose.yaml" ]; then
    TAGS+=("docker")
  fi

  if [ ${#TAGS[@]} -eq 0 ]; then
    echo "No stack tags detected."
  else
    echo -e "${CYAN}Detected stack tags:${NC} ${TAGS[*]}"
  fi
  echo ""

  # Select hooks using Python: tier 1 always, tier 2 only if stack_tags match
  TAGS_JSON=$(python3 -c "import json,sys; print(json.dumps(sys.argv[1:]))" "${TAGS[@]+"${TAGS[@]}"}")

  python3 - "$REGISTRY" "$TAGS_JSON" "$HOOKS_DIR" <<'PYEOF'
import json
import sys

registry_path = sys.argv[1]
detected_tags = json.loads(sys.argv[2])
hooks_dir = sys.argv[3]

with open(registry_path) as f:
    registry = json.load(f)

selected = []
skipped = []

for hook in registry["hooks"]:
    tier = hook["tier"]
    stack_tags = hook.get("stack_tags", [])

    if tier == 1:
        selected.append(hook)
    elif tier == 2:
        matched = [t for t in stack_tags if t in detected_tags]
        if matched:
            selected.append(hook)
        else:
            skipped.append(hook)

print("Selected hooks:")
for h in selected:
    tier_label = f"[tier{h['tier']}]"
    tag_note = ""
    if h.get("stack_tags"):
        tag_note = f"  (tags: {', '.join(h['stack_tags'])})"
    print(f"  + {h['id']} {tier_label}{tag_note}")

if skipped:
    print("")
    print("Skipped hooks (stack tags not detected):")
    for h in skipped:
        print(f"  - {h['id']}  (needs: {', '.join(h.get('stack_tags', []))})")

print("")

# Build Claude Code hooks.json structure
# Group by trigger type
hooks_json = {}

for hook in selected:
    trigger = hook["trigger"]
    script_abs = f"{hooks_dir}/{'/'.join(hook['script'].split('/')[1:])}"
    entry = {
        "command": script_abs
    }
    if hook.get("matcher"):
        matchers = hook["matcher"]
        # Flatten matchers: each one becomes a separate hook entry
        for m in matchers:
            bucket = f"{trigger}:{m}"
            if bucket not in hooks_json:
                hooks_json[bucket] = {"matcher": m, "trigger": trigger, "commands": []}
            hooks_json[bucket]["commands"].append(script_abs)
    else:
        bucket = trigger
        if bucket not in hooks_json:
            hooks_json[bucket] = {"trigger": trigger, "commands": []}
        hooks_json[bucket]["commands"].append(script_abs)

# Render as Claude Code hooks array format
output = {"hooks": {}}

for bucket, info in hooks_json.items():
    trigger = info["trigger"]
    if trigger not in output["hooks"]:
        output["hooks"][trigger] = []

    entry = {"hooks": [{"type": "command", "command": cmd} for cmd in info["commands"]]}
    if "matcher" in info:
        entry["matcher"] = info["matcher"]
    output["hooks"][trigger].append(entry)

print("Generated hooks.json (review before applying to .claude/settings.json or .claude/settings.local.json):")
print("")
print(json.dumps(output, indent=2))
PYEOF

  exit 0
fi

# ─── Normal install mode ─────────────────────────────────────────────────────

echo -e "${BLUE}Claude Flow — Advanced Setup${NC}"
echo ""
echo -e "${CYAN}Note:${NC} Skills are auto-loaded when claude-flow is installed as a Claude Code plugin."
echo "This script installs hooks, scripts, MCP server, and memory files that the plugin"
echo "system does not handle."
echo ""

# Check source files exist
if [ ! -d "$SCRIPT_DIR/skills" ]; then
  echo "Error: skills/ directory not found. Run this from the repo root."
  exit 1
fi

# Install skills (fallback for non-plugin installs)
echo -e "${YELLOW}Installing skills to $SKILLS_DIR/ (fallback — plugin users skip this)${NC}"
mkdir -p "$SKILLS_DIR"

installed=0
for skill_dir in "$SCRIPT_DIR/skills"/*/; do
  skill_name="$(basename "$skill_dir")"
  target="$SKILLS_DIR/$skill_name"

  # Remove existing version
  if [ -d "$target" ]; then
    rm -rf "$target"
  fi

  cp -R "$skill_dir" "$target"
  echo "  + $skill_name"
  installed=$((installed + 1))
done

echo ""

# Install scripts
echo -e "${YELLOW}Installing scripts to $SCRIPTS_DIR/${NC}"
mkdir -p "$SCRIPTS_DIR/hooks"

script_count=0
for script in "$SCRIPT_DIR/scripts"/*.py "$SCRIPT_DIR/scripts"/*.sh; do
  [ -f "$script" ] || continue
  cp "$script" "$SCRIPTS_DIR/"
  chmod +x "$SCRIPTS_DIR/$(basename "$script")"
  echo "  + $(basename "$script")"
  script_count=$((script_count + 1))
done

for hook_script in "$SCRIPT_DIR/scripts/hooks"/*.sh; do
  [ -f "$hook_script" ] || continue
  cp "$hook_script" "$SCRIPTS_DIR/hooks/"
  chmod +x "$SCRIPTS_DIR/hooks/$(basename "$hook_script")"
  echo "  + hooks/$(basename "$hook_script")"
  script_count=$((script_count + 1))
done

echo ""

# Install hooks
echo -e "${YELLOW}Installing hooks to $HOOKS_DIR/${NC}"
mkdir -p "$HOOKS_DIR/tier1"
mkdir -p "$HOOKS_DIR/tier2"

hook_count=0

# Copy registry
cp "$SCRIPT_DIR/hooks/hook-registry.json" "$HOOKS_DIR/hook-registry.json"
echo "  + hook-registry.json"

# Copy tier1 hooks
for hook in "$SCRIPT_DIR/hooks/tier1"/*.sh; do
  [ -f "$hook" ] || continue
  cp "$hook" "$HOOKS_DIR/tier1/"
  chmod +x "$HOOKS_DIR/tier1/$(basename "$hook")"
  echo "  + tier1/$(basename "$hook")"
  hook_count=$((hook_count + 1))
done

# Copy tier2 hooks
for hook in "$SCRIPT_DIR/hooks/tier2"/*.sh; do
  [ -f "$hook" ] || continue
  cp "$hook" "$HOOKS_DIR/tier2/"
  chmod +x "$HOOKS_DIR/tier2/$(basename "$hook")"
  echo "  + tier2/$(basename "$hook")"
  hook_count=$((hook_count + 1))
done

echo ""

# Install memory files (don't overwrite existing — they accumulate data)
MEMORY_DIR="$CLAUDE_DIR/memory"
echo -e "${YELLOW}Installing memory files to $MEMORY_DIR/${NC}"
mkdir -p "$MEMORY_DIR"

memory_count=0
if [ ! -f "$MEMORY_DIR/failure-catalog.md" ]; then
  cp "$SCRIPT_DIR/memory/failure-catalog.md" "$MEMORY_DIR/failure-catalog.md"
  echo "  + failure-catalog.md"
  memory_count=$((memory_count + 1))
else
  echo "  ~ failure-catalog.md (exists, skipped)"
fi

if [ ! -f "$MEMORY_DIR/failure-events.jsonl" ]; then
  touch "$MEMORY_DIR/failure-events.jsonl"
  echo "  + failure-events.jsonl (created empty)"
  memory_count=$((memory_count + 1))
else
  echo "  ~ failure-events.jsonl (exists, skipped)"
fi

if [ ! -f "$MEMORY_DIR/prompt-variants.json" ]; then
  cp "$SCRIPT_DIR/memory/prompt-variants.json" "$MEMORY_DIR/prompt-variants.json"
  echo "  + prompt-variants.json"
  memory_count=$((memory_count + 1))
else
  echo "  ~ prompt-variants.json (exists, skipped)"
fi

if [ ! -f "$MEMORY_DIR/exploration-events.jsonl" ]; then
  touch "$MEMORY_DIR/exploration-events.jsonl"
  echo "  + exploration-events.jsonl (created empty)"
  memory_count=$((memory_count + 1))
else
  echo "  ~ exploration-events.jsonl (exists, skipped)"
fi

echo ""

# Install MCP server
MCP_DIR="$CLAUDE_DIR/mcp/claude-flow"
echo -e "${YELLOW}Installing MCP server to $MCP_DIR/${NC}"
mkdir -p "$MCP_DIR"

cp "$SCRIPT_DIR/mcp/claude-flow-server/server.py" "$MCP_DIR/server.py"
cp "$SCRIPT_DIR/mcp/claude-flow-server/requirements.txt" "$MCP_DIR/requirements.txt"
echo "  + server.py"
echo "  + requirements.txt"

# Install Python dependencies
pip install -r "$MCP_DIR/requirements.txt" --quiet 2>/dev/null || \
  pip3 install -r "$MCP_DIR/requirements.txt" --quiet 2>/dev/null || \
  echo "  ⚠️  Could not install Python dependencies. Run manually: pip install -r $MCP_DIR/requirements.txt"

echo ""
echo -e "${CYAN}MCP Server:${NC}"
echo "  Add this to ~/.claude/settings.json under \"mcpServers\":"
echo ""
echo "  \"claude-flow\": {"
echo "    \"command\": \"python3\","
echo "    \"args\": [\"$HOME/.claude/mcp/claude-flow/server.py\"]"
echo "  }"

# Install reviewer registry
echo -e "${YELLOW}Installing reviewer registry${NC}"
REVIEWER_REG="$CLAUDE_DIR/hooks/claude-flow/reviewer-registry.json"
cp "$SCRIPT_DIR/reviewer-registry.json" "$REVIEWER_REG"
echo "  + reviewer-registry.json"

echo ""

# Suggest project-local plan storage
echo -e "${CYAN}Recommended:${NC} Save plans inside your project (git-tracked) instead of ~/.claude/plans/."
echo "  Add to your project's .claude/settings.json or .claude/settings.local.json:"
echo ""
echo "  {\"plansDirectory\": \"docs/plans\"}"
echo ""

echo -e "${GREEN}Done!${NC} Installed $installed skills, $script_count scripts, $hook_count hooks, $memory_count memory files, and MCP server."
echo ""
echo "Usage:"
echo "  In Claude Code, invoke the workflow with: /claude-flow"
echo "  To generate a hooks.json for the current project: ./install.sh --generate-hooks"
echo ""
echo "Bundled skills:"
for skill_dir in "$SKILLS_DIR"/*/; do
  skill_name="$(basename "$skill_dir")"
  # Check if it was one we installed
  if [ -d "$SCRIPT_DIR/skills/$skill_name" ]; then
    echo "  - $skill_name"
  fi
done
