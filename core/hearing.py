"""
HAL9000 — Hearing
Mic-button-only speech input: click → record → transcribe.
No continuous listening, no wake word.

Supports two STT backends:
  - Whisper API (OpenAI, paid) — fast, accurate
  - faster-whisper (local, free) — runs on CPU via CTranslate2
"""

import io
import wave
from typing import Optional

import numpy as np
import pyaudio

from config import cfg

# Known Whisper hallucination phrases on silence/noise
WHISPER_HALLUCINATIONS = {
    "you", "thank you", "thanks", "thanks for watching",
    "thank you for watching", "you're welcome",
    "bye", "goodbye", "see you", "see you next time",
    "subscribe", "like and subscribe", "please subscribe",
    "so", "the", "i", "okay", "oh", "hmm", "um", "uh",
    "thanks for listening", "music", "applause",
    "foreign", "subtitle", "subtitles",
    "", ".", "...", "-", "--",
}


class Hearing:
    def __init__(self):
        self._audio = pyaudio.PyAudio()

        # STT provider: Whisper API (paid) or faster-whisper (free/local)
        stt = getattr(cfg, "STT_PROVIDER", "whisper_api").lower()
        self._stt_provider = stt

        if stt == "faster_whisper":
            self.client = None
            self._init_faster_whisper()
        else:
            from openai import OpenAI
            self.client = OpenAI(api_key=cfg.OPENAI_API_KEY)
            print("[HAL Hearing] STT: OpenAI Whisper API")

        print("[HAL Hearing] Mic-button mode — click mic to speak")

    def _init_faster_whisper(self):
        """Initialize local faster-whisper model."""
        try:
            from faster_whisper import WhisperModel
            model_size = getattr(cfg, "WHISPER_MODEL_SIZE", "base")
            print(f"[HAL Hearing] Loading faster-whisper '{model_size}' model (FREE, local)...")
            self._whisper_model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
            )
            print(f"[HAL Hearing] STT: faster-whisper '{model_size}' ready (local, free)")
        except ImportError:
            print("[HAL Hearing] ERROR: faster-whisper not installed. Run: pip install faster-whisper")
            print("[HAL Hearing] Falling back to Whisper API...")
            self._stt_provider = "whisper_api"
            from openai import OpenAI
            self.client = OpenAI(api_key=cfg.OPENAI_API_KEY)
        except Exception as e:
            print(f"[HAL Hearing] ERROR loading faster-whisper: {e}")
            self._stt_provider = "whisper_api"
            from openai import OpenAI
            self.client = OpenAI(api_key=cfg.OPENAI_API_KEY)

    # ── Main API: listen_once (mic button) ────────────

    def listen_once(self) -> Optional[str]:
        """
        Record a single utterance from the mic button.
        Waits for speech onset, records until silence, transcribes.
        Returns transcribed text or None.
        """
        print("[HAL Hearing] Mic activated — listening...")

        if not self._wait_for_speech(timeout_seconds=12):
            print("[HAL Hearing] No speech detected")
            return None

        print("[HAL Hearing] Speech detected, recording...")
        frames = self._record_until_silence()
        if not frames:
            print("[HAL Hearing] No speech frames captured")
            return None

        # Energy check — reject quiet noise
        audio_data = b"".join(frames)
        samples = np.frombuffer(audio_data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))

        if rms < cfg.SPEECH_DETECT_RMS * 0.5:
            print(f"[HAL Hearing] Too quiet (rms={rms:.0f})")
            return None

        audio_bytes = self._frames_to_wav(frames)
        text = self._transcribe(audio_bytes)
        return self._filter(text)

    # ── Audio capture ─────────────────────────────────

    def _wait_for_speech(self, timeout_seconds: float = 12) -> bool:
        """Wait for sustained speech energy. Returns True if speech detected."""
        stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=cfg.AUDIO_CHANNELS,
            rate=cfg.AUDIO_SAMPLE_RATE,
            input=True,
            frames_per_buffer=1024,
        )

        detected = False
        consecutive = 0
        required = 3  # ~192ms of sustained speech
        max_chunks = int(cfg.AUDIO_SAMPLE_RATE / 1024 * timeout_seconds)

        for _ in range(max_chunks):
            data = stream.read(1024, exception_on_overflow=False)
            samples = np.frombuffer(data, dtype=np.int16)
            rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))

            if rms >= cfg.SPEECH_DETECT_RMS:
                consecutive += 1
                if consecutive >= required:
                    detected = True
                    break
            else:
                consecutive = 0

        stream.stop_stream()
        stream.close()
        return detected

    def _record_until_silence(self) -> list[bytes]:
        """Record audio frames — stops after 1.5s of silence."""
        stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=cfg.AUDIO_CHANNELS,
            rate=cfg.AUDIO_SAMPLE_RATE,
            input=True,
            frames_per_buffer=1024,
        )

        frames = []
        silent_chunks = 0
        speech_chunks = 0
        max_chunks = int(cfg.AUDIO_SAMPLE_RATE / 1024 * cfg.MIC_RECORD_SECONDS)
        silence_limit = int(cfg.AUDIO_SAMPLE_RATE / 1024 * 1.5)

        for _ in range(max_chunks):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
            amplitude = np.frombuffer(data, dtype=np.int16).max()

            if amplitude < cfg.SILENCE_THRESHOLD:
                silent_chunks += 1
                if silent_chunks >= silence_limit and speech_chunks > 5:
                    break
            else:
                silent_chunks = 0
                speech_chunks += 1

        stream.stop_stream()
        stream.close()

        return frames if speech_chunks >= 3 else []

    def _frames_to_wav(self, frames: list[bytes]) -> bytes:
        """Convert raw PCM frames to a WAV file in memory."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(cfg.AUDIO_CHANNELS)
            wf.setsampwidth(self._audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(cfg.AUDIO_SAMPLE_RATE)
            wf.writeframes(b"".join(frames))
        return buf.getvalue()

    # ── Transcription ─────────────────────────────────

    def _transcribe(self, audio_bytes: bytes) -> Optional[str]:
        """Route to Whisper API or faster-whisper."""
        if self._stt_provider == "faster_whisper":
            return self._transcribe_local(audio_bytes)
        return self._transcribe_api(audio_bytes)

    def _transcribe_api(self, audio_bytes: bytes) -> Optional[str]:
        """Send WAV bytes to OpenAI Whisper API."""
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
            print(f"[HAL Hearing] Whisper API error: {e}")
            return None

    def _transcribe_local(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribe WAV bytes locally with faster-whisper."""
        try:
            audio_file = io.BytesIO(audio_bytes)
            segments, info = self._whisper_model.transcribe(
                audio_file,
                language="en",
                beam_size=1,
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                print(f"[HAL Heard] {text}")
            return text or None
        except Exception as e:
            print(f"[HAL Hearing] faster-whisper error: {e}")
            return None

    # ── Filtering ─────────────────────────────────────

    def _filter(self, text: Optional[str]) -> Optional[str]:
        """Filter out Whisper hallucinations and too-short transcriptions."""
        if not text:
            return None

        cleaned = text.lower().strip().rstrip('.!?,')

        if cleaned in WHISPER_HALLUCINATIONS:
            print(f"[HAL Hearing] Filtered hallucination: '{text}'")
            return None

        if len(cleaned) < 3:
            print(f"[HAL Hearing] Filtered too-short: '{text}'")
            return None

        return text

    # ── Public transcription (for browser mic flow) ─────

    def transcribe_audio(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribe pre-recorded audio bytes (WAV format).
        Used by the browser mic flow where recording happens client-side."""
        text = self._transcribe(audio_bytes)
        return self._filter(text)

    def close(self):
        if hasattr(self, "_audio") and self._audio:
            self._audio.terminate()
