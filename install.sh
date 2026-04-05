#!/usr/bin/env bash
set -euo pipefail

# Claude Flow — Code Creation Workflow installer
# Copies all skills and scripts to ~/.claude/

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_HOME:-$HOME/.claude}"
SKILLS_DIR="$CLAUDE_DIR/skills"
SCRIPTS_DIR="$CLAUDE_DIR/scripts"

# Colors (if terminal supports them)
if [ -t 1 ]; then
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  BLUE='\033[0;34m'
  NC='\033[0m'
else
  GREEN='' YELLOW='' BLUE='' NC=''
fi

echo -e "${BLUE}Claude Flow — Code Creation Workflow Installer${NC}"
echo ""

# Check source files exist
if [ ! -d "$SCRIPT_DIR/skills" ]; then
  echo "Error: skills/ directory not found. Run this from the repo root."
  exit 1
fi

# Install skills
echo -e "${YELLOW}Installing skills to $SKILLS_DIR/${NC}"
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
echo -e "${GREEN}Done!${NC} Installed $installed skills and $script_count scripts."
echo ""
echo "Usage:"
echo "  In Claude Code, invoke the workflow with: /code-creation-workflow"
echo ""
echo "Bundled skills:"
for skill_dir in "$SKILLS_DIR"/*/; do
  skill_name="$(basename "$skill_dir")"
  # Check if it was one we installed
  if [ -d "$SCRIPT_DIR/skills/$skill_name" ]; then
    echo "  - $skill_name"
  fi
done
