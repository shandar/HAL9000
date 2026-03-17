#!/usr/bin/env bash
# HAL9000 — Register MCP server with Claude Code
#
# Run this once to give Claude Code access to HAL's capabilities:
#   chmod +x setup_mcp.sh && ./setup_mcp.sh
#
# After registration, every Claude Code session can use HAL's tools:
#   hal_see, hal_speak, hal_listen, hal_screenshot, hal_remember, etc.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"

# Check prerequisites
if ! command -v claude &> /dev/null; then
    echo "❌ Claude Code CLI not found."
    echo "   Install: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ HAL9000 venv not found at ${VENV_PYTHON}"
    echo "   Run: python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

echo "🔴 Registering HAL9000 MCP server with Claude Code..."
echo ""
echo "   Server: ${SCRIPT_DIR}/hal_mcp_server.py"
echo "   Python: ${VENV_PYTHON}"
echo ""

# Register the MCP server
# Using scope "user" so it's available in all Claude Code sessions
claude mcp add hal-9000 \
    --scope user \
    -- "$VENV_PYTHON" "${SCRIPT_DIR}/hal_mcp_server.py"

echo ""
echo "✅ HAL9000 MCP server registered!"
echo ""
echo "Available tools in Claude Code:"
echo "   hal_see           — Capture webcam frame"
echo "   hal_screenshot    — Capture macOS screen"
echo "   hal_speak         — Speak with HAL's cloned voice"
echo "   hal_listen        — Listen via microphone + transcribe"
echo "   hal_remember      — Store persistent memory"
echo "   hal_recall        — Search memories"
echo "   hal_forget        — Remove memories"
echo "   hal_list_memories — List all memories"
echo "   macos_volume      — Get/set system volume"
echo "   macos_brightness  — Get/set display brightness"
echo "   macos_notify      — Send macOS notification"
echo "   macos_clipboard   — Get/set clipboard"
echo "   macos_apps        — List/open/quit applications"
echo "   macos_wifi        — Get WiFi network"
echo "   macos_battery     — Get battery status"
echo "   hal_web_search    — Search the web"
echo "   hal_fetch_url     — Fetch webpage content"
echo "   hal_time          — Get current time"
echo ""
echo "Try it: open Claude Code and ask 'What do you see on my webcam?'"
echo "        or 'HAL, announce that the build is done'"
