"""
HAL9000 — Brain
Claude claude-sonnet-4-5 with vision. Manages conversation history and builds
multimodal messages (text + frame image).
"""

from typing import Optional

import anthropic

from config import cfg


class Brain:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=cfg.ANTHROPIC_API_KEY)
        self.history: list[dict] = []

    def think(self, user_text: str, frame_b64: Optional[str] = None) -> str:
        """
        Send user text + optional webcam frame to Claude.
        Returns HAL's response as a string.
        """
        content = self._build_content(user_text, frame_b64)
        self.history.append({"role": "user", "content": content})
        self._trim_history()

        try:
            response = self.client.messages.create(
                model=cfg.CLAUDE_MODEL,
                max_tokens=cfg.MAX_TOKENS,
                system=cfg.SYSTEM_PROMPT,
                messages=self.history,
            )
            reply = response.content[0].text
            # Store assistant reply as text-only (images not kept in history)
            self.history.append({"role": "assistant", "content": reply})
            print(f"[HAL] {reply}")
            return reply

        except anthropic.APIError as e:
            err = f"I seem to be having a small problem, Dave. Error: {e}"
            print(f"[HAL Brain] API error: {e}")
            return err

    def _build_content(self, text: str, frame_b64: Optional[str]) -> list[dict]:
        """Build the content array for the user message."""
        if frame_b64:
            return [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": frame_b64,
                    },
                },
                {"type": "text", "text": text},
            ]
        return [{"type": "text", "text": text}]

    def _trim_history(self):
        """Keep history within the configured limit."""
        limit = cfg.CONVERSATION_HISTORY_LIMIT * 2
        if len(self.history) > limit:
            self.history = self.history[-limit:]

    def reset(self):
        """Clear conversation history."""
        self.history = []
        print("[HAL Brain] Memory cleared.")
