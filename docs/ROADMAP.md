# HAL 9000 — Roadmap

> Prioritized feature roadmap. Items are ordered by impact and feasibility.

---

## Current State (v1.1)

HAL is a fully functional local multimodal AI agent with:
- Webcam vision, mic hearing, multi-provider LLM brain
- 3 voice providers (Edge TTS, ElevenLabs, XTTS) with runtime hot-swap
- 31 OS-level tools with security hardening (command whitelist, AppleScript escaping)
- Browser-based dashboard with chat UI, choice sheet disambiguation, waveform on HAL image
- Click-to-listen mic button as wake word fallback
- App discovery (`list_installed_apps`) and AppleScript automation (`app_action`)
- Claude Code split into interactive Terminal (`open_claude_code`) and silent delegation
- MCP server for Claude Code/Desktop integration
- PWA support for mobile access
- Persistent memory across sessions
- Time-aware creative boot greetings

---

## Phase 1: Core Polish (High Impact, Low Effort) — ✅ COMPLETED

### 1.1 Wake Word Detection ✅
**Status:** Implemented

- Two-stage "Hey HAL" detection: VAD → short Whisper check → keyword match
- Supports "Hey HAL", "HAL", "Hello HAL", "OK HAL" trigger phrases
- Handles common Whisper mishearings ("hey pal", "hey how", etc.)
- Inline command support: "Hey HAL, what time is it?" works in one utterance
- Configurable via `WAKE_WORD_ENABLED` (default: true)
- No extra dependencies — uses existing Whisper API with ~2s clips (~$0.0002/check)
- Falls back to always-listening mode with `WAKE_WORD_ENABLED=false`
- UI badge shows current mode (Wake / Always)

### 1.2 Conversation Context Window ✅
**Status:** Implemented

- Token-aware trimming via `_estimate_tokens()` (~4 chars/token heuristic)
- `CONTEXT_MAX_TOKENS=16000` configurable budget
- Tool output compression: old tool results truncated to `TOOL_RESULT_MAX_CHARS=1500`
- Drops oldest messages when over budget (keeps last 2 for current exchange)

### 1.3 Split `core/tools.py` into Modules ✅
**Status:** Implemented

872-line monolith split into 7 domain modules:
```
core/tools/
├── __init__.py       # Registry, execute(), format converters, security helpers
├── shell.py          # run_shell
├── apps.py           # open/quit/list applications, open URLs
├── files.py          # list/read/write/search/info
├── macos.py          # volume, brightness, notifications, clipboard, screenshot
├── web.py            # web_search, fetch_url
├── memory.py         # remember, recall, forget, list_memories
└── delegation.py     # delegate_to_claude_code
```
All 31 tools registered. All external imports unchanged.

### 1.5 Click-to-Listen Mic Button ✅
**Status:** Implemented

- Mic button in chat window for instant voice recording
- Bypasses wake word — goes straight to Whisper STT
- Reliable fallback when "Hey HAL" detection struggles

### 1.6 Choice Sheet Disambiguation UI ✅
**Status:** Implemented

- Slide-up modal with backdrop blur for presenting numbered options
- Auto-detects disambiguation choices in HAL's response using heuristics
- Strips choice lists from chat bubble (shows only the question)
- Server-side TTS stripping via `_strip_choices_for_tts()` — HAL never reads options aloud
- Smart detection avoids false positives on informational numbered lists

### 1.7 App Discovery & Automation ✅
**Status:** Implemented

- `list_installed_apps` — Scans macOS app directories, optional search filter
- `app_action` — AppleScript `tell...end tell` blocks for controlling running apps
- Security blocklist: `do shell script`, `run script`, `system events`, `keystroke`

### 1.8 Claude Code Tool Split ✅
**Status:** Implemented

- `open_claude_code` — Opens visible Terminal window with Claude Code CLI (5s debounce)
- `delegate_to_claude_code` — Silent background execution with `--print` flag
- Disambiguation prompt when user says "open Claude Code" (desktop app vs terminal CLI)

### 1.9 HAL Image Controls & Waveform ✅
**Status:** Implemented

- Waveform visualization overlaid precisely on HAL image red block
- JS-computed positioning accounts for CSS `object-fit: contain` letterboxing
- 3D-style Vision/Hearing/Voice buttons on HAL image blank strip
- Camera panel collapses when vision is off, HAL image expands full height
- `ResizeObserver` dynamically repositions overlays on resize

### 1.10 Creative Boot Greetings ✅
**Status:** Implemented

- Time-aware salutations (morning/afternoon/evening/midnight)
- 20 randomized HAL-style boot lines
- Personalized with creator's name

### 1.4 Error Notification UI ✅
**Status:** Implemented

Toast notification system in the dashboard:
- Error toasts for LLM failures, tool errors, connection issues
- Warning toasts for SSE disconnection
- Auto-dismiss after 5 seconds, max 5 visible
- Slide-in/out animations with color-coded types (error/warn/info)
- Errors from SSE log stream auto-detected and surfaced

---

## Phase 2: Intelligence Upgrades (High Impact, Medium Effort)

### 2.1 Vision Analysis Modes
**Priority:** High
**Effort:** Medium

Add specialized vision modes beyond "describe what you see":
- **Object tracking** — Track specific objects across frames
- **Change detection** — Alert when something changes on desk/screen
- **Document reading** — OCR documents placed in front of camera
- **Whiteboard capture** — Photograph and digitize whiteboard sketches

### 2.2 Multi-Turn Tool Planning
**Priority:** High
**Effort:** Medium

Enable HAL to plan multi-step tool sequences before executing:
- "Deploy the project" → plan: git status → npm build → deploy → verify
- Show the plan in the chat UI for approval before execution
- Rollback capability if a step fails

### 2.3 Proactive Observations
**Priority:** Medium
**Effort:** Medium

Let HAL occasionally comment on what it sees without being asked:
- "You've been staring at that error for 3 minutes. Would you like help?"
- "I notice you have 47 browser tabs open. Shall I help organize?"
- Configurable frequency and triggers
- Opt-in setting: `PROACTIVE_MODE=true`

### 2.4 RAG over Knowledge Base
**Priority:** Medium
**Effort:** High

Replace whole-document injection with retrieval-augmented generation:
- Chunk knowledge files into embeddings
- Use vector similarity to retrieve relevant chunks per query
- Supports much larger knowledge bases (currently limited by context window)
- Local embeddings via sentence-transformers or OpenAI embeddings API

---

## Phase 3: Integrations (Medium Impact, Medium Effort)

### 3.1 Calendar Integration
**Priority:** High
**Effort:** Medium

New tools:
- `get_calendar` — Today's events, upcoming meetings
- `create_event` — Schedule a new event
- `next_meeting` — "What's my next meeting?"

Options: Google Calendar API, Apple Calendar via AppleScript, or CalDAV.

### 3.2 Email/Slack Integration
**Priority:** Medium
**Effort:** Medium

New tools:
- `read_emails` — Recent unread emails (subject, sender, preview)
- `send_email` — Compose and send email (confirm safety)
- `send_slack` — Post to a Slack channel

### 3.3 Smart Home Control
**Priority:** Low
**Effort:** Medium

New tools via HomeKit/Home Assistant:
- `lights` — Control smart lights
- `thermostat` — Set temperature
- `media` — Control TV/speakers

### 3.4 GitHub Integration
**Priority:** Medium
**Effort:** Low

New tools:
- `gh_prs` — List open PRs
- `gh_issues` — List/create issues
- `gh_status` — CI/CD status

Can leverage the `gh` CLI already available on macOS.

---

## Phase 4: Advanced Features (High Impact, High Effort)

### 4.1 Screen Understanding
**Priority:** High
**Effort:** High

Instead of just screenshots, HAL understands what's on screen:
- Parse active window content (code editor, browser, design tool)
- Understand UI state — "you're on the settings page of Figma"
- Respond to "what am I looking at?" with app-aware context
- Use vision model to read text from screenshots

### 4.2 Voice Cloning Pipeline
**Priority:** Medium
**Effort:** High

Streamline XTTS voice cloning:
- Record 10 samples from the dashboard UI
- Auto-process into training clips
- One-click train a custom voice
- Save and select from multiple voice profiles

### 4.3 Multi-Agent Collaboration
**Priority:** Medium
**Effort:** High

HAL coordinates with other AI agents:
- Delegate sub-tasks to specialized agents (code review, research, design)
- Claude Code delegation already works — extend to other tools
- Agent-to-agent communication protocol
- Task queue with progress tracking

### 4.4 Persistent Conversation Memory
**Priority:** Medium
**Effort:** High

Move beyond simple facts to full conversation memory:
- Summarize past conversations and store summaries
- Recall relevant past conversations when topics come up again
- "Last time we discussed X, you decided to..."
- Vector DB for semantic search over conversation history

---

## Phase 5: Production Hardening

### 5.1 Authentication
**Priority:** High (if exposed to network)
**Effort:** Low

- JWT or session-based auth for the web dashboard
- API key for programmatic access
- Rate limiting on all endpoints

### 5.2 Logging & Observability
**Priority:** Medium
**Effort:** Low

- Structured logging (JSON) instead of print statements
- Log rotation and retention policies
- Token usage tracking per conversation
- Tool execution audit trail

### 5.3 Testing
**Priority:** Medium
**Effort:** High

- Unit tests for tool execution, safety checks, config validation
- Integration tests for brain → tool → response flow
- Mock LLM responses for deterministic testing
- CI pipeline with linting + tests

### 5.4 Docker/Containerization
**Priority:** Low
**Effort:** Medium

- Dockerfile for reproducible deployment
- Docker Compose with optional GPU support for XTTS
- Volume mounts for memory and knowledge persistence

---

## Feature Request Backlog

Ideas captured but not yet prioritized:

- [ ] **Voice activity visualization** — Mic amplitude meter in the dashboard
- [ ] **Conversation export** — Download conversation as markdown/PDF
- [ ] **Multiple personalities** — Switch between HAL, JARVIS, Friday voice profiles
- [ ] **Keyboard shortcuts** — Dashboard hotkeys (Ctrl+Enter to send, etc.)
- [ ] **Plugin system** — Drop-in Python files that register new tools automatically
- [ ] **Streaming responses** — Token-by-token LLM output in the chat window
- [ ] **Image generation** — Integration with DALL-E or Stable Diffusion
- [ ] **Music control** — Spotify/Apple Music playback control
- [ ] **Pomodoro mode** — HAL manages focus/break cycles with voice prompts
- [ ] **Meeting mode** — HAL takes notes during meetings, summarizes at end
- [ ] **Code review mode** — HAL reviews git diffs and provides feedback
- [ ] **Dashboard themes** — Switch between HAL 9000, JARVIS, Matrix aesthetics

---

## Contributing

When implementing a roadmap item:

1. Create a plan doc in `docs/PLAN-{feature}.md`
2. Get approval before writing code
3. Branch: `feature/{name}`
4. One logical change per commit: `feat(scope): description`
5. Update docs and README when done
6. No `--no-ff` merges to main
