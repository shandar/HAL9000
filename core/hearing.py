"""
HAL9000 — Hearing
Records from mic until silence, transcribes with OpenAI Whisper.
"""

import io
import wave
from typing import Optional

import numpy as np
import pyaudio
from openai import OpenAI

from config import cfg


class Hearing:
    def __init__(self):
        self.client = OpenAI(api_key=cfg.OPENAI_API_KEY)
        self._audio = pyaudio.PyAudio()

    def listen(self) -> Optional[str]:
        """
        Record from mic until silence or max duration.
        Returns transcribed text, or None if nothing heard.
        """
        print("[HAL] Listening...")
        frames = self._record()
        if not frames:
            return None

        audio_bytes = self._frames_to_wav(frames)
        return self._transcribe(audio_bytes)

    def _record(self) -> list[bytes]:
        """Record audio frames — stops on silence or max seconds."""
        stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=cfg.AUDIO_CHANNELS,
            rate=cfg.AUDIO_SAMPLE_RATE,
            input=True,
            frames_per_buffer=1024,
        )

        frames = []
        silent_chunks = 0
        max_chunks = int(cfg.AUDIO_SAMPLE_RATE / 1024 * cfg.MIC_RECORD_SECONDS)
        max_silent = int(cfg.AUDIO_SAMPLE_RATE / 1024 * 1.2)

        for _ in range(max_chunks):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
            amplitude = np.frombuffer(data, dtype=np.int16).max()

            if amplitude < cfg.SILENCE_THRESHOLD:
                silent_chunks += 1
                if silent_chunks >= max_silent and len(frames) > 10:
                    break
            else:
                silent_chunks = 0

        stream.stop_stream()
        stream.close()
        return frames

    def _frames_to_wav(self, frames: list[bytes]) -> bytes:
        """Convert raw PCM frames to a WAV file in memory."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(cfg.AUDIO_CHANNELS)
            wf.setsampwidth(self._audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(cfg.AUDIO_SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()

    def _transcribe(self, audio_bytes: bytes) -> Optional[str]:
        """Send WAV bytes to Whisper, return transcript."""
        try:
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = "audio.wav"
            result = self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",
            )
            text = result.text.strip()
            if text:
                print(f"[HAL Heard] {text}")
            return text or None
        except Exception as e:
            print(f"[HAL Hearing] Transcription error: {e}")
            return None

    def close(self):
        self._audio.terminate()
