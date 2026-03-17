# HAL 9000 — Architecture

## System Overview

HAL 9000 is a local, multimodal AI agent that sees, hears, thinks, speaks, acts, and integrates with external AI tools. It runs on macOS, controls the OS, maintains persistent memory, and exposes its capabilities via both a web dashboard and an MCP server.

```
┌──────────────────────────────────────────────────────────────────┐
│                        HAL9000 ENGINE                            │
│                        (hal9000.py)                              │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────┐    │
│  │  VISION  │  │ HEARING  │  │    VOICE     │  │  TOOLS   │    │
│  │ webcam   │  │ mic+STT  │  │ Edge/11L/XTTS│  │ 31 tools │    │
│  │ OpenCV   │  │ Whisper  │  │ + browser    │  │ + safety │    │
│  └────┬─────┘  └────┬─────┘  │   audio      │  │ + audit  │    │
│       │              │        └──────▲───────┘  └────▲─────┘    │
│       │              │               │               │          │
│       ▼              ▼               │               │          │
│  ┌───────────────────────────────────┴───────────────┴───┐     │
│  │                        BRAIN                           │     │
│  │  ┌─────────┐  ┌───────────┐  ┌─────────┐             │     │
│  │  │ OpenAI  │  │ Anthropic │  │ Gemini  │  ← pick one │     │
│  │  │ GPT-4o  │  │  Claude   │  │  Flash  │             │     │
│  │  └─────────┘  └───────────┘  └─────────┘             │     │
│  │  + function calling → tool execution loop              │     │
│  │  + conversation history (thread-safe)                  │     │
│  │  + knowledge base injection                            │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                  │
│  ┌────────────────────────┐  ┌────────────────────────┐         │
│  │      KNOWLEDGE         │  │       MEMORY           │         │
│  │  knowledge/*.txt       │  │  memory/facts.json     │         │
│  │  + sources.txt (URLs)  │  │  persistent across     │         │
│  │  loaded at boot        │  │  sessions              │         │
│  └────────────────────────┘  └────────────────────────┘         │
└──────────────────────────────────────────────────────────────────┘
         │                              │
         ▼                              ▼
┌─────────────────────┐     ┌─────────────────────┐
│   Flask Web Server   │     │    MCP Server        │
│   localhost:9000     │     │   (hal_mcp_server.py)│
│                      │     │                      │
│   - Dashboard UI     │     │   - 18 MCP tools     │
│   - Chat window      │     │   - Claude Code      │
│   - MJPEG stream     │     │   - Claude Desktop   │
│   - SSE events       │     │   - stdio transport   │
│   - REST API         │     │   - lazy-loaded       │
│   - Browser audio    │     │     subsystems        │
│   - Waveform viz     │     │                      │
└─────────────────────┘     └─────────────────────┘
                                     │
                              ┌──────▼──────┐
                              │ Claude Code  │
                              │ Claude       │
                              │ Desktop      │
                              └─────────────┘
```

---

## Data Flow

### Text Chat Flow (browser → server → brain → voice → browser)

```
User types in chat UI
  → POST /api/chat { text }
  → HALEngine.send_text(text)
  → Brain.think(text, frame?)
    → LLM responds (may call tools in a loop)
  → HALEngine._respond(reply)
    → _speak_to_browser(reply)
      → Voice.synthesize(text) → audio bytes
      → Store in _speech_data with _speech_id++
  → SSE pushes new speech_id to browser
  → Browser fetches /api/speech → decodes → AudioContext → AnalyserNode
  → Real frequency data drives waveform canvas
  → source.onended → POST /api/speech_done
```

### Voice Conversation Flow (mic → STT → brain → TTS → speakers)

```
Hearing._wait_for_speech() → VAD detects audio above threshold
  → Hearing._record_speech() → records until 1.5s silence
  → Whisper STT → text
  → Filter hallucinations (known Whisper artifacts on silence)
  → Brain.think(text, frame)
    → LLM processes with tool definitions
    → If tool_calls → execute → feed results back → repeat
    → Final text response
  → Voice.synthesize(text) → audio bytes → browser playback
  → Post-speech cooldown (1.5s) to avoid echo pickup
```

### MCP Tool Call Flow (Claude Code → MCP server → HAL subsystems)

```
Claude Code calls MCP tool (e.g., hal_see)
  → FastMCP routes to tool function
  → Lazy-loads subsystem on first use (vision, voice, hearing)
  → For hal_see: proxies through localhost:9000/api/frame
  → Returns result to Claude Code
```

---

## Module Responsibilities

| Module | File | Role |
|--------|------|------|
| **Config** | `config.py` | Env loading with safe int/float parsing, validation |
| **Vision** | `core/vision.py` | Webcam capture (OpenCV), JPEG encoding, MJPEG stream |
| **Hearing** | `core/hearing.py` | PyAudio mic recording, VAD, Whisper STT, hallucination filtering |
| **Brain** | `core/brain.py` | LLM providers (OpenAI/Anthropic/Gemini), function calling loop, thread-safe history |
| **Voice** | `core/voice.py` | Multi-provider TTS (Edge/ElevenLabs/XTTS), OS audio playback, browser synthesis |
| **Tools** | `core/tools/` | Tool registry (31 tools across 7 modules), safety layer, command whitelist, AppleScript escaping |
| **Knowledge** | `core/knowledge.py` | Load local files + fetch remote llms.txt URLs |
| **Engine** | `hal9000.py` | Lifecycle, main loop, subsystem toggles, browser audio routing, voice hot-swap, TTS choice stripping, creative boot greetings |
| **Server** | `server.py` | Flask REST API, SSE, MJPEG, chat endpoint, speech serving |
| **MCP Server** | `hal_mcp_server.py` | FastMCP server exposing 18 tools to Claude Code/Desktop |
| **UI** | `templates/index.html` | Dashboard, chat, waveform visualizer, choice sheet, HAL image controls |

---

## Security Architecture

### Command Execution

```
User request → LLM decides tool → tools.execute()
                                      │
                                      ▼
                              ┌───────────────┐
                              │ Safety Check   │
                              │                │
                              │ safe → run     │
                              │ confirm → ask  │
                              │ dangerous → ⚠  │
                              └───────┬───────┘
                                      │
                              ┌───────▼───────┐
                              │ run_shell()    │
                              │                │
                              │ shlex.split()  │  ← no shell=True
                              │ whitelist check│  ← 77 allowed commands
                              │ blocklist check│  ← sudo, shutdown blocked
                              │ subprocess.run │  ← argument list only
                              └───────────────┘
```

### AppleScript Injection Prevention

All user-controlled strings passed to `osascript -e` are escaped via `_escape_applescript()` which neutralizes `"` and `\` characters, preventing breakout from AppleScript string contexts.

### Network Isolation

Flask binds to `127.0.0.1` by default. Override with `HAL_HOST=0.0.0.0` only if you understand the risk (exposes all endpoints to LAN).

---

## Threading Model

```
Main Thread          ─── Flask web server (threaded=True)
  └── Request threads  ─── One per HTTP request

Engine Thread        ─── HALEngine._loop() (daemon)
  ├── Vision polling   ─── Frame capture every FRAME_INTERVAL seconds
  ├── Hearing          ─── Blocking listen() call
  └── Brain.think()    ─── LLM API call + tool loop

Speech Thread        ─── _speak_to_browser() (daemon, per utterance)
  └── Voice.synthesize() → stores audio for browser fetch

SSE Generator        ─── One per connected browser tab
  └── Polls engine status every 1s
```

**Thread Safety:**
- `_speech_lock` protects `_speech_data` and `_speech_id`
- `_log_lock` protects the conversation log list
- `_history_lock` protects brain conversation history
- `_tts_lock` protects lazy XTTS model loading (double-checked locking)

---

## Web Server API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Dashboard UI |
| `/api/status` | GET | Engine status (running, subsystems, camera, voice provider) |
| `/api/start` | POST | Boot HAL engine |
| `/api/stop` | POST | Shutdown HAL engine |
| `/api/toggle/<sub>` | POST | Toggle vision/hearing/voice |
| `/api/voice_provider` | GET/POST | Get or switch voice provider (edge/elevenlabs/local) |
| `/api/chat` | POST | Send text message, get HAL's reply |
| `/api/speech` | GET | Fetch latest synthesized audio (binary) |
| `/api/speech_done` | POST | Browser signals audio playback finished |
| `/api/frame` | GET | Single webcam frame as base64 JPEG |
| `/api/log` | GET | Conversation log (with `?since=` timestamp filter) |
| `/api/stream` | GET | SSE stream (status + log updates, 1Hz) |
| `/api/video` | GET | MJPEG webcam stream (~20fps) |

---

## Browser Audio Pipeline

```
Server synthesizes TTS → stores audio bytes + increments speech_id
  → SSE pushes new speech_id to browser
  → Browser fetches /api/speech (binary audio)
  → AudioContext.decodeAudioData()
  → BufferSource → AnalyserNode → AudioDestination (speakers)
                        │
                        ▼
                  analyser.getByteFrequencyData()
                        │
                        ▼
                  Canvas waveform visualization
                  (32 bars, real FFT frequency data)
                        │
                        ▼
                  source.onended → POST /api/speech_done
                  (signals server to clear _speaking flag)
```

This architecture ensures:
1. Audio plays through the browser (not server speakers)
2. Waveform visualization uses real frequency data from Web Audio API
3. The hearing loop pauses during playback to avoid echo pickup

---

## UI Architecture

### Waveform Positioning (object-fit: contain)

The waveform canvas overlays the red block in the HAL image. Since `object-fit: contain` creates letterboxing, CSS percentage positioning fails. Instead, JS computes the rendered image bounds:

```
Known image dimensions: 850 × 1236px
Red block at: x=124-729, y=1016-1160 (in image pixels)

wfResize():
  1. Get panel dimensions
  2. Compute rendered image size (preserving aspect ratio)
  3. Compute letterbox offsets (centered)
  4. Position waveform at (offset + fraction × rendered size)
  5. ResizeObserver re-triggers on panel resize
```

### HAL Image Controls

Three 3D-style buttons (Vision, Hearing, Voice) are positioned on the blank strip below the HAL eye (y=880-1000 in image pixels). They use the same JS positioning logic as the waveform. States: active (lit) / disabled (dimmed), with press animation.

### Camera Panel Collapse

When vision is toggled off, the camera panel smoothly collapses (`flex: 0; height: 0; opacity: 0`) and the HAL image expands to fill the full height. `ResizeObserver` re-triggers waveform and button positioning.

### Choice Sheet (Disambiguation)

Slide-up modal with backdrop blur for disambiguation choices. Auto-detected by `parseChoices()` which identifies numbered options in HAL's response using heuristics:
- Items must be short labels (< 80 chars)
- 2–6 items only (not educational lists)
- Sequential numbering starting at 1
- Items cannot contain multiple sentences

When detected, the numbered list is stripped from the chat bubble (only the question title is shown) and the choice sheet presents clickable options. TTS also strips choice lists server-side via `_strip_choices_for_tts()` regex.

### Boot Greetings

`HALEngine._generate_greeting()` produces time-aware, creative HAL-style greetings. 20 randomized boot lines combined with time-appropriate salutations (morning/afternoon/evening/late night).
