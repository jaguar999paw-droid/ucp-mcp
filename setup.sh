#!/usr/bin/env bash
# setup.sh — bootstrap ucp-mcp venv and install dependencies
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> Creating Python venv..."
python3 -m venv venv

echo "==> Installing dependencies..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q

mkdir -p logs

echo ""
echo "Setup complete!"
echo ""
echo "Start the UCP backend (Docker):"
echo "  docker compose up -d"
echo ""
echo "Verify it's running:"
echo "  curl http://localhost:8100/.well-known/ucp | python3 -m json.tool"
echo ""
echo "The MCP server entry is already written to your Claude Desktop configs."
echo "Restart Claude Desktop to activate ucp-mcp."
