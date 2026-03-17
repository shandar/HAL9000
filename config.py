"""
HAL9000 — Config
All settings loaded from environment. Import this everywhere.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # API keys
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")

    # Vision
    FRAME_INTERVAL: float = float(os.getenv("FRAME_INTERVAL", "2.0"))
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))

    # Audio input
    MIC_RECORD_SECONDS: int = int(os.getenv("MIC_RECORD_SECONDS", "5"))
    SILENCE_THRESHOLD: int = int(os.getenv("SILENCE_THRESHOLD", "500"))
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1

    # Claude
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"
    MAX_TOKENS: int = 1024
    CONVERSATION_HISTORY_LIMIT: int = 10  # keep last N exchanges

    # Identity
    HAL_NAME: str = os.getenv("HAL_NAME", "HAL")

    # HAL system prompt
    SYSTEM_PROMPT: str = f"""You are {os.getenv("HAL_NAME", "HAL")}, a calm, highly intelligent AI assistant.
You can see the user through a webcam and hear their voice.
You speak in the composed, precise manner of HAL 9000 — never flustered, always helpful.

When given a frame from the webcam:
- Describe what you observe if asked
- Identify objects, people (by description, not by name unless told), scenes
- Answer questions about what you can see

Keep responses concise and spoken — you are speaking aloud, not writing.
No bullet points or markdown. Short, clear sentences only.
Never break character. Never say you cannot see — you always have the current frame."""

    @classmethod
    def validate(cls) -> list[str]:
        """Return list of missing required keys."""
        missing = []
        if not cls.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")
        if not cls.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if not cls.ELEVENLABS_API_KEY:
            missing.append("ELEVENLABS_API_KEY")
        if not cls.ELEVENLABS_VOICE_ID:
            missing.append("ELEVENLABS_VOICE_ID")
        return missing


cfg = Config()
