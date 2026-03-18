# HAL 9000 — Changelog

All notable changes to this project are documented here.

---

## [1.4.0] — 2026-03-19

### Added — Streaming, Voice, Commands

#### Token Streaming
- **Real-time streaming responses** — tokens appear word-by-word as the LLM generates them
- **`/api/chat/stream`** SSE endpoint — streams `token`, `tool`, `done` events
- **Streaming `think_stream()`** method on OpenAI brain with tool call support
- **Chunked TTS** — sentences spoken as they complete, not after full response
- **TTS queue** — thread-safe `queue.Queue` prevents audio overlap
- **List detection** — TTS stops before numbered/bulleted lists (intro only)

#### Browser Microphone
- **Browser-side mic recording** via Web Audio API (`getUserMedia` + `ScriptProcessorNode`)
- **Live waveform** during recording — cyan bars on HAL's red block
- **Silence auto-detection** — 1.5s silence → auto-stop recording
- **Click-to-stop** — click mic again to stop early
- **WAV encoding** in pure JS — no server-side pyaudio needed for web UI
- **`/api/transcribe`** endpoint — accepts audio blob, returns transcription
- **Mic stops HAL speaking** — clicking mic cancels any playing audio

#### Slash Commands
- **35 slash commands** — type `/` in chat for full categorized menu
- **Categories**: System, Memory, Voice, Vision, Apps, Control, Claude, Files, Web, Workspace
- **Arrow key navigation**, Enter to execute, Tab to autocomplete, Escape to close
- **Filter by typing** — `/vo` filters to `/voice`, `/volume`, `/vision`

#### UI Improvements
- **Terminal-style chat** — monospace, left-aligned, prompt prefixes (`>` HAL, `$` user, `#` system, `~` tool)
- **Formatted lists** — numbered and bulleted lists render as styled items (inline lists auto-split)
- **Terminal-style choice sheet** — flat, minimal, amber title, hover borders
- **Status pill** — centered above input, shows recording/transcribing/thinking phases
- **Workspace actions** — Run, Edit, Copy, Send to Claude, Download, Regenerate
- **Mini terminal output** — code execution results in terminal-style panel
- **Inline code editor** — edit artifacts with Tab indentation support
- **HAL image power button** — 4 buttons: Power, Vision, Voice, Claude with tooltips

#### Smart Features
- **Dynamic user name** — first-boot onboarding asks "What shall I call you?", remembers forever
- **Fresh memory in system prompt** — `@property` rebuilds prompt on each think() with latest memories
- **Parallel tool execution** — `ThreadPoolExecutor(4)` for multi-tool calls
- **Processing guard** — prevents concurrent messages, auto-expires after 180s
- **History auto-repair** — `_repair_history()` fixes orphaned tool_calls on error
- **Honesty rule** — system prompt prevents hallucinating features/commands

### Changed
- Mic input: server-side pyaudio → browser Web Audio API (web UI)
- Chat: bubble style → terminal style with prompt prefixes
- Choice sheet: glass-morphism modal → flat terminal selection
- TTS: full-response → sentence-by-sentence chunked
- `MAX_TOKENS`: 1024 → 2048 (artifacts no longer truncated)
- Grid layout: `1fr 1fr` → `1fr 2fr` (more chat width)
- System prompt: hardcoded "Shandar" → dynamic from memory
- Error messages: "Dave" → removed
- Tool descriptions: "Mac" → "computer" (cross-platform)
- `escapeHtml()`: creates DOM element per call → reuses single element
- `wfDraw()`: 60fps always → idle skip (200ms setTimeout when inactive)
- `wfResize()`: debounced window resize, live ResizeObserver for smooth transitions

### Removed
- Continuous listening / wake word detection
- `WAKE_WORD_ENABLED` config
- `hearing_enabled` toggle
- Hearing button from HAL image
- Browser TTS fallback (caused voice mismatch)
- Header power button (moved to HAL image)
- Dead code: `_load_memories`, `_save_memories`, `MEMORY_DIR` in tools/__init__
- Dead config: `CONVERSATION_HISTORY_LIMIT`
- Dead CSS: `.power-btn` (72 lines)

### Fixed
- **Engine reference bug** — `from server import engine` created duplicate instances; replaced with `set_engine()` pattern
- **API key leak** — `ANTHROPIC_API_KEY` stripped from Claude Code subprocess env (uses Max plan OAuth)
- **History corruption** — `_thinking_lock` on all brain providers + `_repair_history()` auto-heals
- **Audio overlap** — `currentSource.stop()` before new playback + TTS queue
- **XSS in task/agent panels** — all dynamic content escaped via `escapeHtml()`
- **SSE JSON.parse** — wrapped in try/catch (malformed JSON no longer kills handler)
- **`postMessage` origin check** — artifact runner validates message origin
- **Processing lock stuck** — 180s auto-expire prevents permanent lock
- **Double messages** — `streamingUntil` timestamp dedup prevents SSE re-rendering streamed messages
- **Service worker cache** — network-first for HTML, no-cache headers on `/`
- **Slash command `//`** — strip leading `/` from textContent before prepending

### Security
- Hardcoded macOS PATH → `os.environ.get("PATH")` in code execution
- `postMessage` origin validation on artifact runner
- No-cache headers on HTML to prevent stale JS

---

## [1.3.0] — 2026-03-18

### Added — Free Mode + Cross-Platform

#### Free Mode (zero API keys)
- **`FREE_MODE=true`** — one toggle switches brain, STT, and TTS to free alternatives
- **`OllamaBrain`** class in `core/brain.py` — local LLM via Ollama with native tool calling
- **faster-whisper** integration in `core/hearing.py` — local Whisper STT via CTranslate2
- **Config**: `OLLAMA_MODEL` (llama3.1), `OLLAMA_BASE_URL`, `STT_PROVIDER`, `WHISPER_MODEL_SIZE`
- **Auto-fallback** — if faster-whisper isn't installed, falls back to Whisper API
- **Cascade override** — FREE_MODE overrides AI_PROVIDER, STT_PROVIDER, TTS_PROVIDER; individual overrides still work

#### Cross-Platform (Windows + Linux)
- **Platform abstraction layer** — `core/platform/` with auto-detection via `platform.system()`
- **`core/platform/base.py`** — abstract `PlatformAPI` interface (15 methods)
- **`core/platform/mac.py`** — macOS implementation (AppleScript, osascript)
- **`core/platform/windows.py`** — Windows implementation (PowerShell, WMI, Toast, PIL)
- **`core/platform/linux.py`** — Linux implementation (pactl, xclip, notify-send, brightnessctl)
- **`core/tools/system.py`** — replaces `macos.py` with platform-neutral tool wrappers
- **Cross-platform app discovery** — .app (mac), Start Menu/.lnk (Windows), .desktop (Linux)
- **Cross-platform terminal** — Terminal.app (mac), Windows Terminal/cmd (Windows), gnome-terminal/konsole (Linux)
- **Claude CLI binary detection** — searches platform-specific paths on all OSes

#### Landing Page
- **Interactive tutorial** section with 5 animated scenario tabs (Voice, Chat, Tools, Co-Work, Memory)
- **Animated conversation flows** with staggered message reveals and tool call indicators
- **Memory timeline** with color-coded type indicators
- **Expandable use case cards** for 6 tool categories
- **Split into 3 files**: `landing.html` + `assets/landing.css` + `assets/landing.js`

### Changed
- `core/tools/macos.py` → `core/tools/system.py` (platform-neutral)
- `core/tools/apps.py` refactored to use `platform` API
- `core/tools/delegation.py` uses `platform.open_terminal()` for cross-platform Terminal
- `hal_mcp_server.py` system tools route through `platform` API
- `create_brain()` factory accepts `"ollama"` provider
- `config.validate()` skips API key checks for Ollama/faster-whisper
- Brain providers: 3 → 4 (added Ollama)
- README.md: added HAL eye hero image, Free Mode section, Cross-Platform table

---

## [1.2.0] — 2026-03-18

### Added — Co-Work Platform

#### Phase 1: Typed Memory + Session Context
- **Typed memory store** (`core/memory_store.py`) — entries have `id`, `type`, `content`, `timestamp`, `source`, `session_id`, `metadata`
- **Memory types**: `fact`, `decision`, `preference`, `task`, `session_summary`
- **Auto-migration** from legacy `{fact, timestamp}` format — zero breaking changes
- **Session tracking** — session ID, tools-ran list, auto-summarize on HAL shutdown
- **`save_session` tool** — manual "wrap up" context capture
- **MCP `hal_save_session`** — Claude Code saves session context for handoff
- **MCP `hal_get_context`** — Claude Code loads recent sessions + decisions + preferences at start
- **Brain prompt** groups memories by type, includes "RECENT SESSIONS" section

#### Phase 2: Background Task Runner
- **`core/task_runner.py`** — async queue with `subprocess.Popen`, real-time stdout progress, cancellation
- **`background_task` tool** — submit long-running Claude Code tasks asynchronously
- **`list_tasks` tool** — show all tasks with status
- **`cancel_task` tool** — cancel queued or running tasks
- **API**: `GET/POST /api/tasks`, `POST /api/tasks/<id>/cancel`
- **Task queue panel** — collapsible UI with status dots, elapsed time, cancel buttons
- **Config**: `TASK_TIMEOUT` (600s), `MAX_CONCURRENT_TASKS` (2)

#### Phase 3: Shared Workspace (Artifacts)
- **`core/tools/artifacts.py`** — `create_artifact` (code/markdown/html/mermaid/json) and `update_artifact`
- **API**: `GET /api/artifacts`, `GET /api/artifacts/<id>`
- **Workspace panel** — tabbed interface with copy/close buttons
- **3-column grid layout** when artifacts exist
- **Mermaid rendering** via CDN, HTML in sandboxed iframe

#### Phase 4: Multi-Agent Orchestration
- **`core/orchestrator.py`** — named agents, conflict detection, result summarization
- **`orchestrate` tool** — spawn multiple Claude Code agents on parallel tasks
- **`list_agents` + `check_conflicts` tools**
- **API**: `GET /api/agents`, `GET /api/agents/conflicts`, `POST /api/agents/<id>/cancel`
- **Agent dashboard** — cyan-accented cards with status, file lists, cancel controls
- **Config**: `MAX_AGENTS` (4)

### Changed
- Tool count: 31 → 40 (+9 new tools)
- MCP tool count: 18 → 20 (+2 new MCP tools)
- `hal_remember` MCP tool accepts `type` and `source` params
- `hal_recall` and `hal_list_memories` accept `type` filter
- SSE stream extended with `tasks`, `agents`, `artifact_version`

---

## [1.1.0] — 2026-03-18

### Added
- **Choice sheet UI** — Slide-up disambiguation modal with backdrop blur; auto-detects numbered options in HAL's response and presents clickable choices
- **Smart choice detection** — Heuristics distinguish disambiguation options (short labels, 2-6 items) from informational numbered lists to prevent false positives
- **TTS choice stripping** — Server-side regex (`_strip_choices_for_tts()`) removes numbered lists before TTS synthesis so HAL never reads options aloud
- **App discovery** — `list_installed_apps` tool scans macOS app directories with optional search filter
- **App automation** — `app_action` tool sends AppleScript `tell...end tell` blocks to control running applications (Word, Safari, TextEdit, etc.)
- **AppleScript security blocklist** — `app_action` blocks dangerous patterns: `do shell script`, `run script`, `system events`, `keystroke`
- **Claude Code split** — Two distinct tools: `open_claude_code` (visible Terminal, 5s debounce) and `delegate_to_claude_code` (silent `--print` mode)
- **Click-to-listen mic button** — Chat UI mic button bypasses wake word for instant voice recording
- **HAL image waveform** — Waveform visualization overlaid precisely on the red block in the HAL image using JS-computed positioning
- **HAL image controls** — 3D-style Vision/Hearing/Voice buttons positioned on the blank strip below the HAL eye
- **Camera collapse** — Camera panel smoothly collapses when vision is off; HAL image expands to full height
- **Creative boot greetings** — Time-aware salutations + 20 randomized HAL-style boot lines personalized with creator's name
- **Power button** — Circular SVG power icon in top toolbar replaces text-based activate button
- **ResizeObserver** — Dynamic repositioning of waveform and controls when HAL panel resizes

### Changed
- Tool count increased from 28 to 31
- Tools module split from monolith (`core/tools.py`) into 7 domain modules (`core/tools/`)
- Subsystem toggles moved from top toolbar to HAL image controls
- System prompt updated with disambiguation rules (present choices, don't read them aloud)
- Choice sheet styling: white text instead of red for less visual aggression

### Fixed
- Waveform overflow — CSS percentage positioning replaced with JS pixel-computed positioning to account for `object-fit: contain` letterboxing
- Duplicate Terminal windows — 5-second debounce guard on `open_claude_code`
- Echo pickup — 1.5s post-speech cooldown prevents mic from capturing HAL's own output
- Word text insertion — Changed from single-line to multi-line AppleScript `tell...end tell` blocks
- HAL image button clipping — Removed `translateY` on `:active` state, reduced button size

---

## [1.0.0] — 2026-03-17

### Added
- **Core engine** — HAL9000 lifecycle management with thread-safe start/stop/toggle
- **Multi-provider brain** — GPT-4o (OpenAI), Claude (Anthropic), Gemini support with function calling
- **Vision** — Webcam capture via OpenCV with MJPEG streaming and base64 encoding
- **Hearing** — PyAudio mic recording with VAD (voice activity detection) + OpenAI Whisper STT
- **Voice** — 3 TTS providers: Edge TTS (free), ElevenLabs (paid), XTTS (local voice cloning)
- **Browser audio pipeline** — TTS synthesis → browser fetch → AudioContext → AnalyserNode → waveform canvas
- **28 OS-level tools** — Shell commands, file operations, macOS system controls, web search, persistent memory, Claude Code delegation
- **Tool security** — Command whitelist (77 approved), blocklist, AppleScript escaping, secret file blocking
- **Wake word detection** — "Hey HAL" two-stage detection: VAD → short Whisper check → keyword match
- **Context window management** — Token-aware trimming with configurable budget (16K default)
- **Knowledge base** — Local files + remote llms.txt URLs loaded at boot
- **Persistent memory** — Facts stored in `memory/facts.json`, survives restarts
- **Web dashboard** — Sci-fi industrial UI with chat window, webcam HUD, waveform visualizer
- **MCP server** — 18 tools exposed to Claude Code/Desktop via FastMCP
- **PWA support** — Service worker + manifest for mobile home screen install
- **Error toasts** — Slide-in notification system for LLM/tool/connection errors
