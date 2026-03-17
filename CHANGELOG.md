# HAL 9000 — Changelog

All notable changes to this project are documented here.

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
