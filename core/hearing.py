"""
HAL9000 — Hearing
Records from mic only when speech is detected, transcribes with OpenAI Whisper.
Includes voice activity detection to prevent Whisper hallucinations on silence.

Wake Word Mode (default on):
  When WAKE_WORD_ENABLED=true, HAL listens for "Hey HAL" (or just "HAL") before
  recording a full command. Uses a two-stage approach:
    1. Energy-based VAD detects any speech (free, instant)
    2. Short clip sent to Whisper for keyword check (~$0.0002 per check)
    3. If "hal" detected → records the actual command

  Set WAKE_WORD_ENABLED=false to use the original always-listening mode.
"""

import io
import re
import wave
from typing import Optional

import numpy as np
import pyaudio
from openai import OpenAI

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

# Wake word keywords — if ANY of these appear anywhere in the trigger
# transcription, we consider it a wake word activation.
# We use simple substring matching after normalizing punctuation.
WAKE_KEYWORDS = {"hal", "how", "pal"}

# More specific phrases for higher confidence matching
WAKE_PHRASES = {
    "hey hal", "hello hal", "ok hal", "okay hal", "hi hal",
    "hey how", "hey pal", "hey hell", "hey al",
    "a]hal", "heyhal",
}


def _normalize(text: str) -> str:
    """Normalize text for wake word matching: lowercase, strip punctuation."""
    return re.sub(r'[^a-z0-9\s]', '', text.lower()).strip()


class Hearing:
    def __init__(self):
        self._audio = pyaudio.PyAudio()
        self.wake_word_enabled = cfg.WAKE_WORD_ENABLED

        # STT provider: Whisper API (paid) or faster-whisper (free/local)
        stt = getattr(cfg, "STT_PROVIDER", "whisper_api").lower()
        self._stt_provider = stt

        if stt == "faster_whisper":
            self.client = None  # no OpenAI client needed
            self._init_faster_whisper()
        else:
            self.client = OpenAI(api_key=cfg.OPENAI_API_KEY)
            print(f"[HAL Hearing] STT: OpenAI Whisper API")

        if self.wake_word_enabled:
            print(f"[HAL Hearing] Wake word mode ON — say 'Hey HAL' to activate")
            print(f"[HAL Hearing] SPEECH_DETECT_RMS={cfg.SPEECH_DETECT_RMS}, SILENCE_THRESHOLD={cfg.SILENCE_THRESHOLD}")
            print(f"[HAL Hearing] Set WAKE_WORD_ENABLED=false for always-listening mode")
        else:
            print("[HAL Hearing] Always-listening mode (no wake word)")

    def _init_faster_whisper(self):
        """Initialize local faster-whisper model."""
        try:
            from faster_whisper import WhisperModel
            model_size = getattr(cfg, "WHISPER_MODEL_SIZE", "base")
            print(f"[HAL Hearing] Loading faster-whisper '{model_size}' model (FREE, local)...")
            # Use int8 for speed on CPU, float16 if CUDA available
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
            self.client = OpenAI(api_key=cfg.OPENAI_API_KEY)
        except Exception as e:
            print(f"[HAL Hearing] ERROR loading faster-whisper: {e}")
            self._stt_provider = "whisper_api"
            self.client = OpenAI(api_key=cfg.OPENAI_API_KEY)

    @property
    def mode(self) -> str:
        """Return the current listening mode for status display."""
        return "wake_word" if self.wake_word_enabled else "always_listen"

    def listen(self) -> Optional[str]:
        """
        Wait for speech, record until silence, transcribe.
        Returns transcribed text, or None if nothing meaningful heard.
        """
        if self.wake_word_enabled:
            return self._listen_with_wake_word()
        return self._listen_always()

    # ── Single-shot listen (mic button, no wake word) ──

    def listen_once(self) -> Optional[str]:
        """
        Record a single utterance — no wake word check.
        Used when the user explicitly clicks the mic button.
        Waits for speech, records until silence, transcribes.
        """
        print("[HAL Hearing] Mic button — listening for speech...")

        if not self._wait_for_speech(timeout_chunks=200):  # ~13 seconds
            print("[HAL Hearing] No speech detected")
            return None

        print("[HAL Hearing] Speech detected, recording...")
        frames = self._record_speech()
        if not frames:
            print("[HAL Hearing] No speech frames captured")
            return None

        # Energy check
        audio_data = b"".join(frames)
        samples = np.frombuffer(audio_data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))

        if rms < cfg.SPEECH_DETECT_RMS * 0.5:
            print(f"[HAL Hearing] Too quiet (rms={rms:.0f})")
            return None

        audio_bytes = self._frames_to_wav(frames)
        text = self._transcribe(audio_bytes)
        return self._filter_transcription(text)

    # ── Wake Word Mode ────────────────────────────────

    def _listen_with_wake_word(self) -> Optional[str]:
        """
        Two-stage wake word detection:
          1. VAD detects speech energy
          2. Record short trigger clip (~3s)
          3. Quick Whisper check for "hal" keyword
          4. If matched → record full command
        """
        # Stage 1: Wait for any speech energy
        if not self._wait_for_speech(timeout_chunks=150):
            return None

        print("[HAL Hearing] Speech detected, checking for wake word...")

        # Stage 2: Record a trigger clip (up to 3 seconds)
        trigger_frames = self._record_trigger()
        if not trigger_frames:
            print("[HAL Hearing] Trigger too short, ignoring")
            return None

        # Stage 3: Quick energy check on trigger
        trigger_data = b"".join(trigger_frames)
        samples = np.frombuffer(trigger_data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
        peak = int(np.abs(samples).max())

        if rms < cfg.SPEECH_DETECT_RMS * 0.5:
            print(f"[HAL Hearing] Trigger too quiet (rms={rms:.0f}), ignoring")
            return None

        print(f"[HAL Hearing] Trigger captured: {len(trigger_frames)} chunks, rms={rms:.0f}, peak={peak}")

        # Stage 4: Quick Whisper transcription of trigger clip
        trigger_wav = self._frames_to_wav(trigger_frames)
        trigger_text = self._transcribe(trigger_wav)

        if not trigger_text:
            print("[HAL Hearing] Whisper returned empty for trigger")
            return None

        # Stage 5: Check if trigger contains wake word
        normalized = _normalize(trigger_text)
        print(f"[HAL Hearing] Trigger text: '{trigger_text}' → normalized: '{normalized}'")

        # Check for wake word: "hal" must appear in the text
        is_wake = self._check_wake_word(normalized)

        if not is_wake:
            print(f"[HAL Hearing] No wake word in '{normalized}', ignoring")
            return None

        print(f"[HAL Hearing] *** WAKE WORD DETECTED: '{trigger_text}' ***")

        # Check if the trigger clip already contains a command after the wake word
        # e.g., "Hey HAL, what time is it?" — the full sentence was in the trigger
        command = self._extract_command_from_trigger(normalized)
        if command and len(command) > 3:
            print(f"[HAL Hearing] Inline command: '{command}'")
            return command

        # Stage 6: Wake word was standalone — record the follow-up command
        print("[HAL Hearing] Listening for command...")
        frames = self._record_speech()
        if not frames:
            print("[HAL Hearing] No command speech recorded")
            return None

        # Energy check
        audio_data = b"".join(frames)
        samples = np.frombuffer(audio_data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
        peak = np.abs(samples).max()

        if rms < 300 or peak < cfg.SILENCE_THRESHOLD:
            print(f"[HAL Hearing] Command too quiet (rms={rms:.0f})")
            return None

        # Transcribe the command
        audio_bytes = self._frames_to_wav(frames)
        text = self._transcribe(audio_bytes)

        return self._filter_transcription(text)

    def _check_wake_word(self, normalized: str) -> bool:
        """Check if normalized text contains a wake word."""
        # Check exact phrases first
        for phrase in WAKE_PHRASES:
            if phrase in normalized:
                return True

        # Check if "hal" appears as a word (not inside "shall", "shallow", etc.)
        words = normalized.split()
        for word in words:
            if word in ("hal", "haal", "howl"):
                return True

        # Check two-word combos: "hey" + wake keyword
        for i in range(len(words) - 1):
            if words[i] in ("hey", "hi", "hello", "ok", "okay"):
                if words[i + 1] in WAKE_KEYWORDS:
                    return True

        return False

    def _record_trigger(self) -> list[bytes]:
        """
        Record a short clip (~3 seconds) to check for wake word.
        Longer than before to capture full "Hey HAL" utterance.
        """
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
        # 3 seconds max for trigger detection
        max_chunks = int(cfg.AUDIO_SAMPLE_RATE / 1024 * 3.0)
        # 1.2s silence = stop (give time for natural pauses)
        max_silent = int(cfg.AUDIO_SAMPLE_RATE / 1024 * 1.2)

        for _ in range(max_chunks):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
            amplitude = np.frombuffer(data, dtype=np.int16).max()

            if amplitude < cfg.SILENCE_THRESHOLD:
                silent_chunks += 1
                if silent_chunks >= max_silent and speech_chunks > 2:
                    break
            else:
                silent_chunks = 0
                speech_chunks += 1

        stream.stop_stream()
        stream.close()

        if speech_chunks < 2:
            return []

        return frames

    def _extract_command_from_trigger(self, normalized: str) -> Optional[str]:
        """
        If the trigger clip contains both wake word and a command,
        extract just the command part.
        e.g., "hey hal what time is it" → "what time is it"
        """
        # Try removing known wake phrases from the start
        for phrase in sorted(WAKE_PHRASES, key=len, reverse=True):
            if normalized.startswith(phrase):
                remainder = normalized[len(phrase):].strip()
                if remainder and len(remainder) > 3:
                    return remainder

        # Try removing "hey hal" / "hal" patterns
        patterns = [
            r'^(?:hey|hi|hello|ok|okay)\s+(?:hal|how|pal|al)\s+',
            r'^hal\s+',
        ]
        for pattern in patterns:
            match = re.match(pattern, normalized)
            if match:
                remainder = normalized[match.end():].strip()
                if remainder and len(remainder) > 3:
                    return remainder

        return None

    # ── Always-Listening Mode ─────────────────────────

    def _listen_always(self) -> Optional[str]:
        """Original always-listening mode (no wake word)."""
        if not self._wait_for_speech():
            return None

        frames = self._record_speech()
        if not frames:
            return None

        audio_data = b"".join(frames)
        samples = np.frombuffer(audio_data, dtype=np.int16)
        rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
        peak = np.abs(samples).max()

        if rms < 300 or peak < cfg.SILENCE_THRESHOLD:
            return None

        audio_bytes = self._frames_to_wav(frames)
        text = self._transcribe(audio_bytes)
        return self._filter_transcription(text)

    # ── Shared Audio Helpers ──────────────────────────

    def _filter_transcription(self, text: Optional[str]) -> Optional[str]:
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

    def _wait_for_speech(self, timeout_chunks: int = 100) -> bool:
        """
        Listen passively until sustained speech energy is detected.
        Uses RMS (root mean square) instead of peak amplitude for stability.
        Requires consecutive above-threshold chunks to filter noise spikes.
        Each chunk is ~64ms at 16kHz/1024 buffer.
        """
        stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=cfg.AUDIO_CHANNELS,
            rate=cfg.AUDIO_SAMPLE_RATE,
            input=True,
            frames_per_buffer=1024,
        )

        detected = False
        consecutive = 0
        required = 3  # ~192ms of sustained speech energy

        for _ in range(timeout_chunks):
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

    def _record_speech(self) -> list[bytes]:
        """Record audio frames once speech is detected — stops on silence."""
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
        max_silent = int(cfg.AUDIO_SAMPLE_RATE / 1024 * 1.5)  # 1.5s silence = stop

        print("[HAL] Recording...")

        for _ in range(max_chunks):
            data = stream.read(1024, exception_on_overflow=False)
            frames.append(data)
            amplitude = np.frombuffer(data, dtype=np.int16).max()

            if amplitude < cfg.SILENCE_THRESHOLD:
                silent_chunks += 1
                if silent_chunks >= max_silent and speech_chunks > 5:
                    break
            else:
                silent_chunks = 0
                speech_chunks += 1

        stream.stop_stream()
        stream.close()

        if speech_chunks < 3:
            return []

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
        """Transcribe WAV bytes — routes to Whisper API or faster-whisper."""
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
                beam_size=1,  # faster, slightly less accurate
                vad_filter=True,  # skip silence segments
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                print(f"[HAL Heard] {text}")
            return text or None
        except Exception as e:
            print(f"[HAL Hearing] faster-whisper error: {e}")
            return None

    def close(self):
        if hasattr(self, "_audio") and self._audio:
            self._audio.terminate()
