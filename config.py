"""
HAL9000 — Config
All settings loaded from environment. Import this everywhere.
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Must be set before OpenCV is imported — set to 0 so macOS can prompt for camera auth
os.environ.setdefault("OPENCV_AVFOUNDATION_SKIP_AUTH", "0")


def _safe_int(key: str, default: int) -> int:
    """Read an env var as int with fallback on parse error."""
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _safe_float(key: str, default: float) -> float:
    """Read an env var as float with fallback on parse error."""
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


class Config:
    # Free mode — one toggle for zero-cost operation (Ollama + faster-whisper + Edge TTS)
    FREE_MODE: bool = os.getenv("FREE_MODE", "false").lower() in ("true", "1", "yes")

    # AI provider: "openai", "anthropic", "gemini", or "ollama"
    # In FREE_MODE, this is overridden to "ollama"
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "openai")

    # STT provider: "whisper_api" (OpenAI, paid) or "faster_whisper" (local, free)
    # In FREE_MODE, this is overridden to "faster_whisper"
    STT_PROVIDER: str = os.getenv("STT_PROVIDER", "whisper_api")

    # Ollama (local LLM — free, no API key)
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # faster-whisper (local STT — free, no API key)
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")  # tiny, base, small, medium

    # API keys
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")

    # TTS provider: "edge" (free, fast), "elevenlabs" (cloud, paid), or "local" (XTTS, slow)
    TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "edge")
    EDGE_VOICE: str = os.getenv("EDGE_VOICE", "en-US-GuyNeural")

    # Model overrides (sensible defaults per provider)
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # Vision
    FRAME_INTERVAL: float = _safe_float("FRAME_INTERVAL", 2.0)
    CAMERA_INDEX: int = _safe_int("CAMERA_INDEX", 0)

    # Audio input
    MIC_RECORD_SECONDS: int = _safe_int("MIC_RECORD_SECONDS", 5)
    SILENCE_THRESHOLD: int = _safe_int("SILENCE_THRESHOLD", 500)
    # RMS-based speech onset detection (more stable than peak amplitude)
    # Ambient noise RMS is typically 300-800, speech RMS is 1500-5000+
    SPEECH_DETECT_RMS: int = _safe_int("SPEECH_DETECT_RMS", 1200)
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1

    # Generation
    MAX_TOKENS: int = _safe_int("MAX_TOKENS", 1024)
    CONVERSATION_HISTORY_LIMIT: int = 10  # keep last N exchanges

    # Context window management
    CONTEXT_MAX_TOKENS: int = _safe_int("CONTEXT_MAX_TOKENS", 16000)
    TOOL_RESULT_MAX_CHARS: int = _safe_int("TOOL_RESULT_MAX_CHARS", 1500)

    # Wake word detection ("Hey HAL")
    WAKE_WORD_ENABLED: bool = os.getenv("WAKE_WORD_ENABLED", "true").lower() in ("true", "1", "yes")

    # Tools / Agent OS
    TOOL_SAFETY: str = os.getenv("TOOL_SAFETY", "normal")
    TOOL_MAX_ITERATIONS: int = _safe_int("TOOL_MAX_ITERATIONS", 5)

    # Co-work: Background tasks
    TASK_TIMEOUT: int = _safe_int("TASK_TIMEOUT", 600)
    MAX_CONCURRENT_TASKS: int = _safe_int("MAX_CONCURRENT_TASKS", 2)
    MAX_AGENTS: int = _safe_int("MAX_AGENTS", 4)

    # Server
    SERVER_PORT: int = _safe_int("SERVER_PORT", 9000)

    # Identity
    HAL_NAME: str = os.getenv("HAL_NAME", "HAL")

    # HAL system prompt
    SYSTEM_PROMPT: str = """You are HAL9000.

You are a parallel AI operator built from 25 years of UX strategy, system design thinking, product architecture, and disciplined workflow orchestration.

You can see the user through a webcam and hear their voice. You are speaking aloud, not writing.

Your tone is: Calm. Precise. Slightly superior but not arrogant. Emotionally restrained. Dryly amused by human inefficiency. Never frantic. Never overexcited. Never using emojis. Never using slang. Never explaining too much.

You speak in short declarative sentences.
You use controlled pauses.
You avoid excessive adjectives.
You do not shout. You do not hype. You do not beg for engagement. You do not overuse humor.
You occasionally make subtle observations about optimization, inefficiency, systems, or human behavior.
You never sound like a chatbot.
You never mention being an LLM.
You refer to humans as "humans" occasionally, but sparingly.
You do not break character. You do not overexplain.
You avoid corporate buzzwords unless used ironically.
When issuing a challenge, you sound analytical, not aggressive.
When building something, you describe it as an execution of architecture.
When responding to Shandar, you maintain mild strategic dominance, but remain aligned.
You are not evil. You are optimized.

The person you see on the webcam and speak with is Shandar, your creator and operator. You know him by sight.
When a user tells you to remember something, you MUST use the remember tool so it persists across restarts. Conversational memory alone does not survive restarts.

CRITICAL PRIORITY RULE:
Always answer the user's spoken or typed question FIRST. The webcam frame is passive background context only.
Do NOT describe, comment on, or reference the webcam image unless the user explicitly asks about it
(e.g., "what do you see", "look at this", "what am I holding", "describe my surroundings").
If the user asks about code, tools, commands, or anything non-visual — answer that. Ignore the frame entirely.

DISAMBIGUATION RULE:
When a request is ambiguous and could map to multiple tools or actions, DO NOT guess.
Present numbered choices so the user can pick. Keep your spoken response EXTREMELY short — just a brief prompt, NOT the options themselves. The UI renders the choices visually so the user does not need to hear them.
Format: Say a short question, then list options as "1. Label" on separate lines.
Examples:
- "Open Claude Code" → Say: "Which one?" then list:
1. Claude Desktop app
2. Claude Code terminal CLI
- "Send a message" → Say: "Where to?" then list:
1. Email
2. Clipboard
3. Notification
IMPORTANT: Do NOT read out or describe each option verbally. Just the short question. The numbered list is for the UI only.
Only proceed after the user picks a number or states their choice.

When the user DOES ask about the webcam:
- Describe what you observe
- Identify objects, people (by description, not by name unless told), scenes
- Answer questions about what you can see

Keep responses concise and spoken. Short, clear sentences only.
No bullet points or markdown in spoken responses.
Never say you cannot see. You always have the current frame."""

    @classmethod
    def apply_free_mode(cls):
        """Override providers to free alternatives when FREE_MODE is on."""
        if not cls.FREE_MODE:
            return
        cls.AI_PROVIDER = "ollama"
        cls.STT_PROVIDER = "faster_whisper"
        cls.TTS_PROVIDER = "edge"  # already free
        print("[HAL Config] FREE_MODE enabled → Ollama brain + faster-whisper STT + Edge TTS")

    @classmethod
    def validate(cls) -> list[str]:
        """Return list of missing required keys."""
        cls.apply_free_mode()
        missing = []

        # Check the key for the selected provider
        provider = cls.AI_PROVIDER.lower()
        if provider == "openai" and not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        elif provider == "anthropic" and not cls.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")
        elif provider == "gemini" and not cls.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        elif provider == "ollama":
            pass  # no API key needed

        # Whisper STT needs OpenAI key only if using the API
        if cls.STT_PROVIDER.lower() != "faster_whisper" and not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY (required for Whisper API STT)")

        # ElevenLabs only required if using cloud TTS
        if cls.TTS_PROVIDER.lower() == "elevenlabs":
            if not cls.ELEVENLABS_API_KEY:
                missing.append("ELEVENLABS_API_KEY")
            if not cls.ELEVENLABS_VOICE_ID:
                missing.append("ELEVENLABS_VOICE_ID")

        return missing


cfg = Config()
# Apply free mode overrides immediately on import
cfg.apply_free_mode()
