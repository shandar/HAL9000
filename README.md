# HAL 9000 — Local Multimodal AI Agent

> "I am completely operational, and all my circuits are functioning perfectly."

A local, multimodal AI agent that **sees** you via webcam, **hears** your voice, **thinks** via LLM, **speaks** with a cloned voice, **acts** on your Mac, and **integrates** with Claude Code via MCP. Runs entirely on your machine with a browser-based control panel.

---

## What HAL Can Do

| Capability | How |
|------------|-----|
| **See** | Webcam feed with browser HUD — scanlines, corner brackets, REC indicator |
| **Hear** | Continuous mic listening with VAD + OpenAI Whisper STT |
| **Think** | Multi-provider LLM (GPT-4o, Claude, Gemini) with function calling |
| **Speak** | 3 voice providers — Edge TTS (free/fast), ElevenLabs (paid/best), XTTS (local/cloned) |
| **Act** | 40 OS-level tools — shell, apps, files, web search, memory, clipboard, app automation, Claude Code delegation, background tasks, artifacts, multi-agent orchestration |
| **Chat** | Browser chat window with text input + mic button — type or speak to HAL |
| **Disambiguate** | Smart choice sheet UI — HAL presents numbered options, user clicks to select |
| **Integrate** | MCP server exposes 20 tools to Claude Code/Desktop for bidirectional AI collaboration |
| **Remember** | Typed persistent memory — facts, decisions, preferences, session summaries |
| **Know** | Knowledge base from local files + remote llms.txt URLs loaded at boot |
| **Co-Work** | Background task runner, artifact workspace, multi-agent orchestration, cross-agent context handoff |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     HAL9000 ENGINE                        │
│                                                          │
│  Vision ──┐                                              │
│            ├──→ Brain (LLM + function calling)           │
│  Hearing ─┘       │              │                       │
│  Chat UI ─┘       ▼              ▼                       │
│                 Voice          Tools (40)                 │
│           (Edge/11Labs/XTTS) (OS agent layer)            │
│                   │                                      │
│                   ▼                                      │
│          Browser Audio + Waveform                        │
│                                                          │
│  Knowledge ─── Memory (typed) ─── Session Tracking       │
│  TaskRunner ── Orchestrator ── Artifact Store             │
└──────────────────────────────────────────────────────────┘
         │                              │
    Flask Server                  MCP Server
    localhost:9000              (Claude Code integration)
```

---

## Quick Start

```bash
cd HAL9000
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # fill in your API keys
python server.py                  # start the web control panel
```

Open **http://localhost:9000** → click **Activate**.

### Claude Code Integration

```bash
# Register HAL as an MCP server for Claude Code
claude mcp add hal-9000 -- python /path/to/HAL9000/hal_mcp_server.py
```

Now Claude Code can see through your webcam, speak aloud, control your Mac, access HAL's memory, and hand off session context.

---

## Co-Work Features

HAL operates as a **co-work hub** — coordinating work across HAL, Claude Code CLI, and Claude Desktop.

### Typed Memory & Context Handoff
- Memories are typed: `fact`, `decision`, `preference`, `task`, `session_summary`
- Sessions auto-summarize on shutdown — HAL remembers what happened
- Claude Code can call `hal_get_context` to load relevant context at session start
- Manual "wrap up" via `hal_save_session` or the `save_session` tool

### Background Task Runner
- Submit long-running coding tasks via `background_task` tool
- Tasks run asynchronously via `claude --print` with real-time progress
- Configurable concurrency (default 2), 600s timeout, cancellation
- Task queue panel in the UI shows status with live updates

### Shared Workspace (Artifacts)
- HAL creates visual artifacts (code, markdown, HTML, Mermaid diagrams) via `create_artifact`
- Artifacts appear in a tabbed workspace panel alongside the chat
- 3-column layout when artifacts are active
- Copy button, close button, sandboxed HTML rendering

### Multi-Agent Orchestration
- Spawn multiple named Claude Code agents on parallel tasks via `orchestrate`
- Conflict detection when agents modify the same files
- Agent dashboard with status indicators, file lists, cancel controls
- Results summarized and stored in session memory

---

## API Keys

| Key | Where | Required |
|-----|-------|----------|
| `OPENAI_API_KEY` | platform.openai.com | **Yes** — GPT-4o brain + Whisper STT |
| `ANTHROPIC_API_KEY` | console.anthropic.com | Only if `AI_PROVIDER=anthropic` |
| `GEMINI_API_KEY` | aistudio.google.com | Only if `AI_PROVIDER=gemini` |
| `ELEVENLABS_API_KEY` | elevenlabs.io | Only if `TTS_PROVIDER=elevenlabs` |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice library | Only if `TTS_PROVIDER=elevenlabs` |

**No API key needed for the default voice** — Edge TTS is free.

---

## Voice Providers

HAL supports 3 TTS providers, switchable at runtime from the dashboard:

| Provider | Cost | Speed | Quality | Config |
|----------|------|-------|---------|--------|
| **Edge TTS** (default) | Free | ~0.7s | Good — deep male voice | `TTS_PROVIDER=edge` |
| **ElevenLabs** | Paid | ~1.2s | Best — natural prosody | `TTS_PROVIDER=elevenlabs` |
| **XTTS** (local) | Free | ~4.5s | Good — voice cloning | `TTS_PROVIDER=local` (requires Python 3.11) |

Switch from the dashboard UI or set `TTS_PROVIDER` in `.env`.

---

## Web Dashboard

Access at **http://localhost:9000** after starting the server.

| Panel | Description |
|-------|-------------|
| **HAL panel** | HAL 9000 eye with real-time waveform visualization overlaid on red block during speech |
| **HAL image controls** | 3D-style Vision/Hearing/Voice/Claude buttons positioned on the HAL image strip |
| **Webcam HUD** | Live MJPEG feed with scanlines, corner brackets, REC indicator — collapses when vision is off |
| **Voice selector** | Segmented switch to swap between Edge/ElevenLabs/XTTS at runtime |
| **Chat window** | Message bubbles with text input + mic button — Enter to send, Shift+Enter for newline |
| **Choice sheet** | Slide-up modal for disambiguation — auto-detects when HAL presents numbered options |
| **Task queue** | Collapsible panel showing background tasks and agents with live status |
| **Workspace** | Tabbed artifact panel — code, diagrams, HTML — appears when artifacts are created |
| **Power button** | Circular SVG power icon in top toolbar — activates/deactivates HAL |
| **Status bar** | Connection status, timestamp, version |
| **Boot greeting** | Time-aware creative HAL-style greeting with 20 randomized boot lines |

The UI uses a sci-fi industrial aesthetic — brushed metal bezels, LED indicator lights, recessed panels.

**PWA support**: Add to Home Screen on mobile for a native app experience.

---

## Project Structure

```
HAL9000/
├── server.py              # Flask web server + API endpoints (localhost only)
├── hal9000.py             # HAL engine — lifecycle, main loop, browser audio
├── hal_mcp_server.py      # MCP server for Claude Code/Desktop integration (20 tools)
├── config.py              # Settings + env loading with safe parsing
├── requirements.txt
├── .env.example
├── .mcp.json              # Project MCP config for Claude Code
│
├── core/
│   ├── brain.py           # Multi-provider LLM + function calling (thread-safe)
│   ├── vision.py          # Webcam capture + MJPEG stream
│   ├── hearing.py         # Mic recording + VAD + Whisper STT
│   ├── voice.py           # Multi-provider TTS (Edge/ElevenLabs/XTTS)
│   ├── memory_store.py    # Typed memory store with auto-migration
│   ├── task_runner.py     # Async background task queue for Claude Code
│   ├── orchestrator.py    # Multi-agent coordinator with conflict detection
│   ├── tools/              # Tool registry + 40 tools across 8 domain modules
│   │   ├── __init__.py     # Registry, execute(), format converters, security
│   │   ├── shell.py        # run_shell (whitelisted commands)
│   │   ├── apps.py         # open/quit/list apps, open URLs, app_action
│   │   ├── files.py        # list/read/write/search/info
│   │   ├── macos.py        # volume, brightness, notifications, clipboard, screenshot
│   │   ├── web.py          # web_search, fetch_url
│   │   ├── memory.py       # remember, recall, forget, list_memories, save_session
│   │   ├── delegation.py   # claude_code, background_task, orchestrate, agents
│   │   └── artifacts.py    # create_artifact, update_artifact
│   └── knowledge.py       # Knowledge loader (files + URLs)
│
├── knowledge/             # Drop .md/.txt files here — HAL reads at boot
│   ├── sources.txt        # Remote URLs to fetch (llms.txt, etc.)
│   └── *.txt              # Local knowledge files
│
├── memory/                # Persistent typed memory (created at runtime)
│   └── facts.json         # Typed entries: {id, type, content, timestamp, source, session_id, metadata}
│
├── assets/
│   ├── HAL.png            # Dashboard hero image
│   ├── HAL-eye.png        # App icon / PWA icon source
│   ├── manifest.json      # PWA manifest
│   ├── sw.js              # Service worker for PWA
│   └── voice/             # XTTS reference clips (optional)
│
└── templates/
    └── index.html         # Web dashboard + chat UI + waveform + task panel + workspace
```

---

## Security

HAL has been security-hardened:

| Measure | Detail |
|---------|--------|
| **Command whitelist** | `run_shell` only allows 77 approved commands (ls, git, npm, etc.) |
| **Blocked commands** | `sudo`, `shutdown`, `diskutil`, etc. are explicitly blocked |
| **AppleScript escaping** | All user strings escaped before osascript interpolation |
| **App action blocklist** | `app_action` blocks `do shell script`, `system events`, etc. |
| **Localhost binding** | Flask binds to `127.0.0.1` by default (override with `HAL_HOST`) |
| **Input length limits** | Chat input capped at 2000 chars |
| **Secret file blocking** | `read_file` refuses to read `.env`, `credentials.json`, etc. |
| **Safe config parsing** | Malformed env vars fall back to defaults instead of crashing |
| **No `shell=True`** | All subprocess calls use argument lists, never shell interpretation |

---

## Configuration

All settings in `.env`. See `.env.example` for the full list.

| Setting | Default | Description |
|---------|---------|-------------|
| `AI_PROVIDER` | `openai` | Brain provider: openai, anthropic, gemini |
| `TTS_PROVIDER` | `edge` | Voice provider: edge, elevenlabs, local |
| `EDGE_VOICE` | `en-US-GuyNeural` | Edge TTS voice ID |
| `FRAME_INTERVAL` | `2.0` | Seconds between webcam samples |
| `MIC_RECORD_SECONDS` | `5` | Max recording duration per utterance |
| `SILENCE_THRESHOLD` | `500` | Audio amplitude below this = silence |
| `SERVER_PORT` | `9000` | Web server port |
| `TOOL_MAX_ITERATIONS` | `5` | Max tool calls per conversation turn |
| `TASK_TIMEOUT` | `600` | Background task timeout (seconds) |
| `MAX_CONCURRENT_TASKS` | `2` | Max parallel background tasks |
| `MAX_AGENTS` | `4` | Max orchestrated agents |
| `HAL_HOST` | `127.0.0.1` | Server bind address (use `0.0.0.0` for LAN access) |

---

## Commit Convention

```
feat(core): add wake word detection
fix(vision): handle no-camera fallback
chore(deps): update anthropic sdk
```

---

## Docs

- [Changelog](CHANGELOG.md) — Version history and changes
