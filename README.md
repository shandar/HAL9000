<p align="center">
  <img src="assets/HAL-eye.png" alt="HAL 9000" width="200">
</p>

<h1 align="center">HAL 9000</h1>

<p align="center">
  <em>"I am completely operational, and all my circuits are functioning perfectly."</em>
</p>

<p align="center">
  <strong>Local, multimodal AI agent</strong> — sees, hears, thinks, speaks, and acts on your machine.<br>
  Cross-platform (macOS, Windows, Linux) · Free mode (zero API keys) · Claude Code co-work hub.
</p>

<p align="center">
  <a href="https://affordance.design/hal9000">Product Page</a> ·
  <a href="#free-mode">Free Mode</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#co-work-features">Co-Work</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

A local, multimodal AI agent that **sees** you via webcam, **hears** your voice, **thinks** via LLM, **speaks** with a cloned voice, **acts** on your machine, and **integrates** with Claude Code via MCP. Runs entirely on your machine with a browser-based control panel.

**Works on macOS, Windows, and Linux.** One codebase, auto-detects OS at runtime.

---

## What HAL Can Do

| Capability | How |
|------------|-----|
| **See** | Webcam feed with browser HUD — scanlines, corner brackets, REC indicator |
| **Hear** | Browser mic recording (Web Audio API, live waveform, silence detection) + Whisper STT (API or local faster-whisper) |
| **Think** | Multi-provider LLM (GPT-4o, Claude, Gemini, **Ollama**) with function calling |
| **Speak** | 3 voice providers — Edge TTS (free/fast), ElevenLabs (paid/best), XTTS (local/cloned) |
| **Act** | 43 cross-platform tools — shell, apps, files, web search, memory, clipboard, app automation, Claude Code delegation, background tasks, artifacts, multi-agent orchestration |
| **Chat** | Terminal-style chat with streaming responses, 35 slash commands (categorized menu, keyboard nav), mic button — type or speak to HAL |
| **Disambiguate** | Smart choice sheet UI — HAL presents numbered options, user clicks to select |
| **Integrate** | MCP server exposes 21 tools to Claude Code/Desktop for bidirectional AI collaboration |
| **Remember** | Typed persistent memory — facts, decisions, preferences, session summaries |
| **Know** | Knowledge upload (drag-drop or button) — PDFs, docs, code, images. BM25 keyword search, deep-read or skim modes. Also loads local files + remote llms.txt URLs at boot |
| **Co-Work** | Background task runner, artifact workspace, multi-agent orchestration, cross-agent context handoff |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     HAL9000 ENGINE                        │
│                                                          │
│  Vision ──┐                                              │
│            ├──→ Brain (LLM + function calling)           │
│  Browser ──┘       │              │                       │
│  Mic + Chat        ▼              ▼                       │
│                 Voice          Tools (43)                 │
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

## Free Mode

Run HAL with **zero API keys** and **zero cost** — fully local operation.

```bash
# 1. Install Ollama (local LLM)
brew install ollama        # macOS
# or: curl -fsSL https://ollama.com/install.sh | sh   # Linux
# or: download from ollama.com                         # Windows

# 2. Pull a model
ollama pull llama3.1

# 3. Set up HAL
git clone https://github.com/shandar/HAL9000.git
cd HAL9000 && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 4. One line in .env
echo "FREE_MODE=true" > .env

# 5. Run
python server.py
```

| Layer | Free Provider | Paid Alternative |
|-------|--------------|------------------|
| **Brain** | Ollama (Llama 3.1, Mistral, Phi-3) | GPT-4o, Claude, Gemini |
| **STT** | faster-whisper (local Whisper) | OpenAI Whisper API |
| **TTS** | Edge TTS (default, always free) | ElevenLabs, XTTS |

`FREE_MODE=true` overrides `AI_PROVIDER`, `STT_PROVIDER`, and `TTS_PROVIDER` in one toggle. You can also mix — e.g., `FREE_MODE=true` with `STT_PROVIDER=whisper_api` for local brain + cloud STT.

---

## Cross-Platform Support

HAL auto-detects your OS and uses the right system commands:

| Feature | macOS | Windows | Linux |
|---------|-------|---------|-------|
| Volume | AppleScript | nircmd / PowerShell | pactl / amixer |
| Brightness | ioreg | WMI | brightnessctl |
| Notifications | osascript | Toast API | notify-send |
| Clipboard | pbcopy/pbpaste | Get/Set-Clipboard | xclip / wl-clipboard |
| Screenshot | screencapture | PIL.ImageGrab | scrot / grim |
| Battery | pmset | psutil / WMI | psutil / sysfs |
| WiFi | networksetup | netsh wlan | nmcli |
| Apps | open -a + .app scan | start + Start Menu scan | gtk-launch + .desktop scan |
| Terminal | AppleScript Terminal | Windows Terminal / cmd | gnome-terminal / konsole |
| Embedded Terminal | ✅ xterm.js + PTY | ❌ External only | ✅ xterm.js + PTY |

No `#ifdef`, no separate builds — one `pip install`, one `python server.py`.

---

## System Requirements

### Minimum (Free Mode — Ollama + faster-whisper)

| Component | Requirement |
|-----------|-------------|
| **OS** | macOS 12+, Windows 10+, or Ubuntu 20.04+ (any modern Linux) |
| **CPU** | 4 cores (Intel i5 / Apple M1 / AMD Ryzen 5 or better) |
| **RAM** | 8 GB (Ollama loads models into memory — llama3.1 8B needs ~5 GB) |
| **Disk** | 6 GB free (3 GB for Ollama model + 1 GB for faster-whisper model + HAL) |
| **Python** | 3.10 or higher |
| **Browser** | Any modern browser (Chrome, Firefox, Safari, Edge) |
| **Microphone** | Required for voice input (built-in or USB) |
| **Webcam** | Optional — required only for vision features |
| **Network** | Not required (fully offline operation) |

### Recommended (Paid Providers — GPT-4o, Claude, ElevenLabs)

| Component | Requirement |
|-----------|-------------|
| **RAM** | 4 GB (no local models loaded) |
| **Disk** | 500 MB free |
| **Network** | Required (API calls to OpenAI/Anthropic/Google) |
| **API Keys** | At least `OPENAI_API_KEY` for GPT-4o + Whisper STT |

### Performance Notes

| Mode | Brain Latency | STT Latency | TTS Latency | RAM Usage |
|------|--------------|-------------|-------------|-----------|
| **Free (Ollama llama3.1)** | ~2-5s (CPU), ~1-2s (Apple Silicon) | ~1-3s (faster-whisper base) | ~0.7s (Edge TTS) | ~5-6 GB |
| **Free (Ollama phi3)** | ~1-2s (CPU) | ~1-3s | ~0.7s | ~3 GB |
| **Paid (GPT-4o)** | ~1-2s (API) | ~0.5s (Whisper API) | ~0.7s (Edge) | ~200 MB |
| **Paid (Claude)** | ~1-3s (API) | ~0.5s | ~1.2s (ElevenLabs) | ~200 MB |

> **Apple Silicon users**: Ollama runs significantly faster on M1/M2/M3/M4 chips with Metal acceleration. An M1 MacBook Air can run llama3.1 8B comfortably.
>
> **GPU users (Linux/Windows)**: Ollama supports NVIDIA CUDA. With a 6 GB+ VRAM GPU, expect 2-3x faster inference than CPU.

---

## Quick Start

```bash
git clone https://github.com/shandar/HAL9000.git
cd HAL9000
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # fill in your API keys (or set FREE_MODE=true)
python server.py                  # start the web control panel
```

Open **http://localhost:9000** → click **Activate**.

> **Free mode?** Just `echo "FREE_MODE=true" > .env` — no API keys needed. See [Free Mode](#free-mode).

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

> **With `FREE_MODE=true`, no API keys are needed at all.** See [Free Mode](#free-mode).

| Key | Where | Required |
|-----|-------|----------|
| `OPENAI_API_KEY` | platform.openai.com | Only if using GPT-4o brain or Whisper API STT |
| `ANTHROPIC_API_KEY` | console.anthropic.com | Only if `AI_PROVIDER=anthropic` |
| `GEMINI_API_KEY` | aistudio.google.com | Only if `AI_PROVIDER=gemini` |
| `ELEVENLABS_API_KEY` | elevenlabs.io | Only if `TTS_PROVIDER=elevenlabs` |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice library | Only if `TTS_PROVIDER=elevenlabs` |

**No API key needed for**: Edge TTS (default voice), Ollama (local LLM), faster-whisper (local STT).

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
| **HAL image controls** | 3D-style Vision/Voice/Claude buttons positioned on the HAL image strip |
| **Webcam HUD** | Live MJPEG feed with scanlines, corner brackets, REC indicator — collapses when vision is off |
| **Voice selector** | Segmented switch to swap between Edge/ElevenLabs/XTTS at runtime |
| **Chat window** | Terminal-style chat with prompt prefixes, streaming responses, formatted lists, mic button — Enter to send, Shift+Enter for newline |
| **Slash commands** | 35 categorized commands with keyboard navigation — type `/` to open menu |
| **Choice sheet** | Slide-up modal for disambiguation — auto-detects when HAL presents numbered options |
| **Task queue** | Collapsible panel showing background tasks and agents with live status |
| **Workspace** | Tabbed artifact panel — code, diagrams, HTML — stacks above chat when artifacts are created |
| **Embedded terminal** | Full interactive xterm.js terminal (PTY-backed) — run shell, Claude Code, review artifacts in-app (macOS/Linux) |
| **Resizable layout** | Drag handles between columns to resize HAL, workspace, and chat panels |
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
├── hal_mcp_server.py      # MCP server for Claude Code/Desktop integration (21 tools)
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
│   ├── terminal_server.py # Embedded WebSocket terminal (xterm.js PTY bridge, port 9001)
│   ├── platform/           # Cross-platform OS abstraction (auto-detected)
│   │   ├── __init__.py     # Auto-detect: Darwin → mac, Windows → windows, Linux → linux
│   │   ├── base.py         # Abstract PlatformAPI interface (15 methods)
│   │   ├── mac.py          # macOS: AppleScript, osascript, pbcopy, screencapture
│   │   ├── windows.py      # Windows: PowerShell, WMI, Toast, PIL.ImageGrab
│   │   └── linux.py        # Linux: pactl, xclip, notify-send, brightnessctl
│   │
│   ├── tools/              # Tool registry + 43 tools across 8 domain modules
│   │   ├── __init__.py     # Registry, execute(), format converters, security
│   │   ├── shell.py        # run_shell (whitelisted commands)
│   │   ├── apps.py         # open/quit/list apps, open URLs, app_action (cross-platform)
│   │   ├── files.py        # list/read/write/search/info
│   │   ├── system.py       # volume, brightness, notifications, clipboard, screenshot (cross-platform)
│   │   ├── web.py          # web_search, fetch_url
│   │   ├── memory.py       # remember, recall, forget, list_memories, save_session
│   │   ├── delegation.py   # claude_code, background_task, orchestrate, agents (cross-platform)
│   │   └── artifacts.py    # create_artifact, update_artifact
│   └── knowledge.py       # Knowledge loader (files + URLs) + upload ingestion + BM25 search
│
├── knowledge/             # Drop files here or upload via UI — HAL indexes at boot + runtime
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
| **Code exec guard** | `/api/run` only accepts requests from localhost (127.0.0.1 / ::1) |
| **WebSocket origin check** | Terminal WebSocket validates origin header — rejects cross-site connections |
| **Input length limits** | Chat input capped at 2000 chars |
| **Secret file blocking** | `read_file` refuses to read `.env`, `credentials.json`, etc. |
| **Safe config parsing** | Malformed env vars fall back to defaults instead of crashing |
| **No `shell=True`** | All subprocess calls use argument lists, never shell interpretation |

---

## Configuration

All settings in `.env`. See `.env.example` for the full list.

| Setting | Default | Description |
|---------|---------|-------------|
| `FREE_MODE` | `false` | One toggle for zero-cost: Ollama + faster-whisper + Edge TTS |
| `AI_PROVIDER` | `openai` | Brain provider: openai, anthropic, gemini, **ollama** |
| `STT_PROVIDER` | `whisper_api` | Speech-to-text: whisper_api (cloud) or **faster_whisper** (local) |
| `TTS_PROVIDER` | `edge` | Voice provider: edge, elevenlabs, local |
| `OLLAMA_MODEL` | `llama3.1` | Ollama model name (when using Ollama brain) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `WHISPER_MODEL_SIZE` | `base` | faster-whisper model: tiny, base, small, medium |
| `EDGE_VOICE` | `en-US-GuyNeural` | Edge TTS voice ID |
| `FRAME_INTERVAL` | `2.0` | Seconds between webcam samples |
| `MIC_RECORD_SECONDS` | `5` | Max recording duration per utterance |
| `SILENCE_THRESHOLD` | `500` | Audio amplitude below this = silence |
| `SERVER_PORT` | `9000` | Web server port |
| `TOOL_MAX_ITERATIONS` | `5` | Max tool calls per conversation turn |
| `TASK_TIMEOUT` | `600` | Background task timeout (seconds) |
| `MAX_CONCURRENT_TASKS` | `2` | Max parallel background tasks |
| `MAX_AGENTS` | `4` | Max orchestrated agents |
| `HAL_TERMINAL_PORT` | `9001` | WebSocket port for embedded terminal |
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
