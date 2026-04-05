#!/usr/bin/env bash
# Trigger: PostToolUse:Edit (Dockerfile*, docker-compose*)
# Stack tag: docker
# Reminds the developer that Docker files changed and containers may need
# to be rebuilt. Does not block.
set -e

FILE="${CLAUDE_FILE_PATH:-}"

echo "[docker-rebuild-reminder] Docker configuration file changed: ${FILE:-unknown}"
echo "  Your containers may be out of date. Consider rebuilding:"
echo ""
echo "    docker-compose build       # rebuild all services"
echo "    docker-compose up --build  # rebuild and restart services"
echo "    docker build .             # rebuild a single image"
echo ""
echo "  If running containers are based on the old image, restart them after rebuilding."

exit 0
