# HAL9000 — Personal AI Agent

> "I am completely operational, and all my circuits are functioning perfectly."

A local AI agent that sees you via webcam, hears you via microphone, thinks via Claude claude-sonnet-4-5 (vision), and speaks back with HAL's iconic calm voice.

---

## Architecture

```
Webcam → Frame sampler  ─┐
                          ├→ Claude claude-sonnet-4-5 (vision + tools) → ElevenLabs voice
Mic    → Whisper STT    ─┘
```

## Setup

```bash
cd HAL9000
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # fill in your 4 API keys
python hal9000.py
```

## API keys needed

| Key | Where |
|-----|-------|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `OPENAI_API_KEY` | platform.openai.com (Whisper) |
| `ELEVENLABS_API_KEY` | elevenlabs.io |
| `ELEVENLABS_VOICE_ID` | Your chosen voice ID from ElevenLabs |

## Project structure

```
HAL9000/
├── hal9000.py          # Entry point — main loop
├── config.py           # All settings + env loading
├── requirements.txt
├── .env.example
├── core/
│   ├── vision.py       # Webcam frame capture + encoding
│   ├── hearing.py      # Mic recording + Whisper STT
│   ├── brain.py        # Claude API — vision + conversation
│   └── voice.py        # ElevenLabs TTS + audio playback
└── README.md
```

## Voice commands

- Say **"reset"** or **"clear memory"** — wipes conversation history
- Say **"goodbye HAL"** — clean shutdown
- Press **q** in the camera window — also quits

## PWP commit convention

```
feat(core): add wake word detection
fix(vision): handle no-camera fallback
chore(deps): update anthropic sdk
```
