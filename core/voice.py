"""
HAL9000 — Voice
Multi-provider TTS: Edge TTS (free, fast), ElevenLabs (cloud, paid),
or Coqui XTTS (local, slow).
Switch via TTS_PROVIDER in .env.

Uses macOS afplay / Linux aplay / cross-platform fallback.
Works reliably from any thread (no pygame/SDL dependency).
"""

import asyncio
import glob
import os
import platform
import subprocess
import tempfile
import threading

from config import cfg


class Voice:
    """Factory-initialized voice — delegates to the configured TTS provider."""

    def __init__(self):
        self._speaking = False
        self._process: subprocess.Popen = None
        self._tts = None

        provider = getattr(cfg, "TTS_PROVIDER", "edge").lower()

        if provider == "elevenlabs":
            self._init_elevenlabs()
        elif provider in ("local", "xtts"):
            self._init_local()
        else:
            # Default: edge (free, fast)
            self._init_edge()

    # ── Edge TTS (free, fast) ──────────────────────────

    def _init_edge(self):
        self._provider = "edge"
        self._edge_voice = getattr(cfg, "EDGE_VOICE", "en-US-GuyNeural")
        print(f"[HAL Voice] Edge TTS provider ready (voice: {self._edge_voice})")

    def _synthesize_edge(self, text: str) -> bytes:
        import edge_tts

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()

        try:
            # edge-tts is async — run in a fresh event loop
            async def _generate():
                comm = edge_tts.Communicate(
                    text,
                    self._edge_voice,
                    rate="-5%",
                    pitch="-3Hz",
                )
                await comm.save(tmp.name)

            # Handle case where we're called from a thread with no event loop
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # We're inside an async context — run in a new thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(lambda: asyncio.run(_generate())).result()
            else:
                asyncio.run(_generate())

            with open(tmp.name, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # ── ElevenLabs (cloud, paid) ───────────────────────

    def _init_elevenlabs(self):
        from elevenlabs.client import ElevenLabs as ElevenLabsClient
        self._provider = "elevenlabs"
        self._client = ElevenLabsClient(api_key=cfg.ELEVENLABS_API_KEY)
        print("[HAL Voice] ElevenLabs provider ready.")

    def _synthesize_elevenlabs(self, text: str) -> bytes:
        audio = self._client.text_to_speech.convert(
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
        return b"".join(audio)

    # ── Coqui XTTS (local, slow) ──────────────────────

    def _init_local(self):
        self._provider = "local"

        voice_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "assets", "voice"
        )
        self._reference_clips = sorted(
            glob.glob(os.path.join(voice_dir, "*.mp3"))
            + glob.glob(os.path.join(voice_dir, "*.wav"))
        )

        if not self._reference_clips:
            print("[HAL Voice] No reference clips — falling back to Edge TTS")
            self._init_edge()
            return

        self._reference_clip = self._reference_clips[0]
        self._tts = None
        self._tts_lock = threading.Lock()

        print(f"[HAL Voice] Local XTTS provider ready ({len(self._reference_clips)} clips)")

    def _get_tts(self):
        if self._tts is not None:
            return self._tts

        with self._tts_lock:
            if self._tts is not None:
                return self._tts

            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
            print("[HAL Voice] Loading XTTS model (may take a moment)...")
            from TTS.api import TTS
            self._tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            print("[HAL Voice] XTTS using CPU")
            return self._tts

    def _synthesize_local(self, text: str) -> bytes:
        tts = self._get_tts()
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()

        try:
            tts.tts_to_file(
                text=text,
                file_path=tmp.name,
                speaker_wav=self._reference_clip,
                language="en",
            )
            with open(tmp.name, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    # ── Common interface ─────────────────────────────

    def synthesize(self, text: str) -> tuple[bytes, str]:
        """Synthesize text to audio bytes. Returns (audio_bytes, suffix)."""
        if self._provider == "edge":
            return self._synthesize_edge(text), ".mp3"
        elif self._provider == "local":
            return self._synthesize_local(text), ".wav"
        else:
            return self._synthesize_elevenlabs(text), ".mp3"

    def speak(self, text: str, blocking: bool = True):
        """Convert text to speech and play it."""
        if not text.strip():
            return

        def _play():
            self._speaking = True
            try:
                audio_bytes, suffix = self.synthesize(text)
                self._play_audio(audio_bytes, suffix)
            except Exception as e:
                print(f"[HAL Voice] TTS error: {e}")
            finally:
                self._speaking = False

        if blocking:
            _play()
        else:
            threading.Thread(target=_play, daemon=True).start()

    def _play_audio(self, audio_bytes: bytes, suffix: str = ".mp3"):
        """Play audio bytes using the OS native player."""
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            tmp.write(audio_bytes)
            tmp.flush()
            tmp.close()

            system = platform.system()
            if system == "Darwin":
                cmd = ["afplay", tmp.name]
            elif system == "Linux":
                cmd = ["aplay", tmp.name]
            else:
                cmd = ["ffplay", "-nodisp", "-autoexit", tmp.name]

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._process.wait(timeout=60)  # prevent infinite hang
        finally:
            self._process = None
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    def close(self):
        """Stop any in-progress playback."""
        if self._process:
            try:
                self._process.terminate()
            except OSError:
                pass
