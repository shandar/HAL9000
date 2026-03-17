"""
HAL9000 — Voice
ElevenLabs TTS with pygame playback.
HAL speaks in a calm, precise baritone.
"""

import io
import threading

import pygame
from elevenlabs.client import ElevenLabs as ElevenLabsClient

from config import cfg


class Voice:
    def __init__(self):
        self.client = ElevenLabsClient(api_key=cfg.ELEVENLABS_API_KEY)
        pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
        self._speaking = False
        print("[HAL Voice] Ready.")

    def speak(self, text: str, blocking: bool = True):
        """Convert text to speech and play it."""
        if not text.strip():
            return

        def _play():
            self._speaking = True
            try:
                audio = self.client.text_to_speech.convert(
                    voice_id=cfg.ELEVENLABS_VOICE_ID,
                    text=text,
                    model_id="eleven_multilingual_v2",
                    voice_settings={
                        "stability": 0.85,
                        "similarity_boost": 0.75,
                        "style": 0.0,
                        "use_speaker_boost": True,
                    },
                )
                audio_bytes = b"".join(audio)
                buf = io.BytesIO(audio_bytes)
                pygame.mixer.music.load(buf)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(50)
            except Exception as e:
                print(f"[HAL Voice] TTS error: {e}")
            finally:
                self._speaking = False

        if blocking:
            _play()
        else:
            threading.Thread(target=_play, daemon=True).start()

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def close(self):
        pygame.mixer.quit()
