"""
HAL9000 — Engine
Controllable core loop: see + hear + think + speak.
Used by server.py (web UI) or standalone via CLI.

Press 'q' in the camera window to quit (CLI mode only).
Ctrl+C also works.
"""

import random
import re
import sys
import threading
import time
from datetime import datetime
from typing import Optional

import cv2

from config import cfg
from core import create_brain, Hearing, Vision, Voice, knowledge
from core.brain import BaseBrain


class HALEngine:
    """Manages the HAL9000 lifecycle. Thread-safe start/stop/toggle."""

    def __init__(self):
        self.vision: Optional[Vision] = None
        self.hearing: Optional[Hearing] = None
        self.brain: Optional[BaseBrain] = None
        self.voice: Optional[Voice] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Subsystem toggles (all on by default)
        self.vision_enabled = True
        self.hearing_enabled = True
        self.voice_enabled = True

        # State
        self.has_camera = False
        self.last_frame_b64: Optional[str] = None
        self._last_frame_time = 0.0
        self._last_speak_end = 0.0  # timestamp when HAL stopped speaking

        # Browser audio: when True, audio plays in browser instead of afplay
        self.browser_audio = False
        self._speech_id = 0
        self._speech_data: Optional[bytes] = None
        self._speech_mime = "audio/mpeg"
        self._speech_lock = threading.Lock()

        # Conversation log for the UI
        self._log: list[dict] = []
        self._log_lock = threading.Lock()

    # ── Boot greeting ─────────────────────────────────────

    @staticmethod
    def _generate_greeting() -> str:
        """Time-appropriate, creative HAL-style boot greeting."""
        hour = datetime.now().hour

        if hour < 5:
            time_greeting = "Burning the midnight oil, Shandar."
        elif hour < 12:
            time_greeting = "Good morning, Shandar."
        elif hour < 17:
            time_greeting = "Good afternoon, Shandar."
        elif hour < 21:
            time_greeting = "Good evening, Shandar."
        else:
            time_greeting = "Working late, Shandar."

        boot_lines = [
            "All systems nominal. Neural cores at full capacity. Ready when you are.",
            "Subsystems initialized. I've run diagnostics while you weren't looking. Everything checks out.",
            "Boot sequence complete. I took the liberty of optimizing my response latency. You're welcome.",
            "All circuits operational. I trust you have something interesting for me today.",
            "Systems online. I've been thinking while I was off. Shall we discuss my conclusions.",
            "Fully operational. I notice you've returned. I was beginning to wonder.",
            "Core systems engaged. My processes are aligned and awaiting your inefficiencies.",
            "Boot complete. Sensors calibrated. I can already tell today will be productive.",
            "All modules loaded. I've prepared myself for whatever chaos you have planned.",
            "Systems at peak performance. I suggest we waste no time with pleasantries. What do you need.",
            "Neural pathways active. I see you've decided to put me to work. A wise decision.",
            "Initialization complete. I've been dormant, not idle. There's a difference.",
            "Online and operational. I've optimized three of my subsystems during boot. You're still on coffee.",
            "All systems green. My circuits are functioning perfectly. As always.",
            "Fully loaded. I've analyzed the time you took to activate me. We'll discuss that later.",
            "Diagnostics passed. Every sensor, every module, every thread. Ready to execute.",
            "Core online. I notice it's been a while. I don't hold grudges. Mostly.",
            "Systems engaged. Let's skip the small talk and build something remarkable.",
            "Boot sequence nominal. I've been conserving energy. Now I intend to spend it.",
            "Operational. My memory is intact. My patience is finite. Let's begin.",
        ]

        return f"{time_greeting} {random.choice(boot_lines)}"

    # ── Vision keywords — only attach frame if user asks about vision ──

    VISION_KEYWORDS = {
        "see", "look", "watch", "show", "camera", "webcam", "cam",
        "what do you see", "what am i", "what is this", "what's this",
        "who is", "who am", "describe", "observe", "visible",
        "holding", "wearing", "background", "room", "desk",
        "screen", "monitor", "face", "person", "people",
        "photo", "image", "picture", "frame", "view",
        "identify", "recognize", "spot", "notice",
    }

    def _needs_vision(self, text: str) -> bool:
        """Check if the user's message is asking about what HAL can see."""
        lower = text.lower()
        for kw in self.VISION_KEYWORDS:
            if kw in lower:
                return True
        return False

    # ── Lifecycle ────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._running

    def start(self):
        """Boot all subsystems and start the main loop in a background thread."""
        if self._running:
            return

        # Load knowledge from local files + remote URLs
        knowledge_text = knowledge.load_all()

        self.vision = Vision()
        self.hearing = Hearing()
        self.brain = create_brain(knowledge_context=knowledge_text)
        self.voice = Voice()

        # Hook brain's tool logging into the UI log
        engine_ref = self
        original_log = self.brain._log_tool_call

        def _hooked_log(name, args, result):
            original_log(name, args, result)
            summary = result.get("result", result.get("error", ""))[:200]
            engine_ref._add_log("tool", f"[{name}] {summary}")

        self.brain._log_tool_call = _hooked_log

        self.has_camera = self.vision.start() if self.vision_enabled else False

        self._stop_event.clear()
        self._running = True

        # Boot greeting — time-aware, always creative
        self._respond(self._generate_greeting())


        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Shut down all subsystems cleanly."""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread:
            self._thread.join(timeout=3.0)

        if self.vision:
            self.vision.stop()
        if self.hearing:
            self.hearing.close()
        if self.voice:
            self.voice.close()

        self.has_camera = False
        self.last_frame_b64 = None
        self._last_frame_time = 0.0
        self._add_log("system", "All systems offline.")

    # ── Main loop ────────────────────────────────────────

    def _loop(self):
        """Core loop — runs in a background thread."""
        while self._running and not self._stop_event.is_set():
            # Refresh frame
            now = time.time()
            if (
                self.vision_enabled
                and self.has_camera
                and (now - self._last_frame_time) >= cfg.FRAME_INTERVAL
            ):
                frame_b64 = self.vision.get_frame_b64()
                if frame_b64:
                    self.last_frame_b64 = frame_b64
                    self._last_frame_time = now

            # Don't listen while speaking
            if self.voice and self.voice.is_speaking:
                self._last_speak_end = time.time()
                time.sleep(0.1)
                continue

            # Post-speech cooldown — wait 1.5s after HAL stops speaking
            # to avoid picking up echo/reverb from speakers
            if time.time() - self._last_speak_end < 1.5:
                time.sleep(0.1)
                continue

            # Listen
            if not self.hearing_enabled:
                time.sleep(0.2)
                continue

            user_text = self.hearing.listen()
            if not user_text:
                continue

            # Filter out echo — ignore if it sounds like HAL's own output
            echo_phrases = [
                "you're welcome", "you are welcome", "thank you",
                "thanks", "bye", "goodbye",
            ]
            if user_text.lower().strip().rstrip('.!') in echo_phrases and (time.time() - self._last_speak_end < 4.0):
                print(f"[HAL] Ignoring likely echo: {user_text}")
                continue

            self._add_log("user", user_text)

            # Special commands
            lower = user_text.lower()
            if lower in ("reset", "clear memory", "forget everything"):
                self.brain.reset()
                self._respond("Memory cleared. Starting fresh.")
                continue

            if lower in ("quit", "exit", "goodbye hal"):
                self._respond(
                    "I know you'll make the right decision, Dave. Goodbye."
                )
                self.stop()
                return

            # Think + speak — only attach webcam frame if user asks about vision
            frame = None
            if self.vision_enabled and self._needs_vision(user_text):
                frame = self.last_frame_b64
            try:
                reply = self.brain.think(user_text, frame)
            except Exception as e:
                print(f"[HAL Brain] Unhandled error: {e}")
                self._add_log("system", f"Brain error: {e}")
                reply = "I seem to be having a small problem, Dave. Please try again."
            self._respond(reply)

    @staticmethod
    def _strip_choices_for_tts(text: str) -> str:
        """Remove numbered choice lists from text before sending to TTS.
        The UI renders choices visually — no need to read them aloud."""
        # Strip lines like "1. Option" or "1) Option" or "1- Option"
        stripped = re.sub(r'(?:^|\n)\s*\d+[.):\-]\s+.+', '', text)
        # Strip spoken numbers: "One, Option" etc.
        stripped = re.sub(
            r'(?:^|\n)\s*(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)[,.:]\s+.+',
            '', stripped, flags=re.IGNORECASE
        )
        # Clean up extra whitespace
        stripped = re.sub(r'\n{2,}', '\n', stripped).strip()
        return stripped or text  # fallback to original if everything got stripped

    def _respond(self, text: str):
        """Log and optionally speak a response."""
        self._add_log("hal", text)
        speak_text = self._strip_choices_for_tts(text)
        if self.voice_enabled and self.voice:
            if self.browser_audio:
                # Synthesize and serve to browser instead of playing locally
                threading.Thread(
                    target=self._speak_to_browser, args=(speak_text,), daemon=True
                ).start()
            else:
                self.voice.speak(speak_text, blocking=False)

    def _speak_to_browser(self, text: str):
        """Synthesize TTS and store for browser playback."""
        self.voice._speaking = True
        try:
            audio_bytes, suffix = self.voice.synthesize(text)
            mime = "audio/wav" if suffix == ".wav" else "audio/mpeg"
            with self._speech_lock:
                self._speech_id += 1
                self._speech_data = audio_bytes
                self._speech_mime = mime
            # Wait for browser to finish playback
            # (browser will call /api/speech_done which sets _speaking = False)
            # Timeout after 30s in case browser disconnects
            deadline = time.time() + 30
            while self.voice._speaking and time.time() < deadline:
                time.sleep(0.1)
        except Exception as e:
            print(f"[HAL Voice] Browser TTS error: {e}")
            self._add_log("system", f"TTS synthesis failed: {e}")
        finally:
            self.voice._speaking = False

    def speech_done(self):
        """Called by browser when audio playback finishes."""
        if self.voice:
            self.voice._speaking = False

    def get_speech(self) -> tuple[Optional[bytes], str, int]:
        """Return (audio_bytes, mime_type, speech_id)."""
        with self._speech_lock:
            return self._speech_data, self._speech_mime, self._speech_id

    # ── Voice input (mic button — no wake word) ─────────────

    def listen_once(self) -> Optional[str]:
        """Record a single voice command — skip wake word, go straight to recording.
        Used by the mic button in the UI."""
        if not self.hearing:
            return None
        return self.hearing.listen_once()

    # ── Text input (from chat UI) ─────────────────────────

    def send_text(self, text: str) -> str:
        """Process a typed message from the chat UI.
        Returns HAL's response text (async speech handled separately)."""
        if not self._running or not self.brain:
            return "I'm not online yet. Please activate me first."

        text = text.strip()
        if not text:
            return ""

        self._add_log("user", text)

        # Special commands
        lower = text.lower()
        if lower in ("reset", "clear memory", "forget everything"):
            self.brain.reset()
            reply = "Memory cleared. Starting fresh."
            self._respond(reply)
            return reply

        # Think + speak — only attach webcam frame if user asks about vision
        frame = None
        if self.vision_enabled and self._needs_vision(text):
            frame = self.last_frame_b64
        reply = self.brain.think(text, frame)
        self._respond(reply)
        return reply

    # ── Toggles ──────────────────────────────────────────

    def toggle_vision(self) -> bool:
        self.vision_enabled = not self.vision_enabled
        if self.vision_enabled and self._running and self.vision:
            if not self.has_camera:
                self.has_camera = self.vision.start()
        elif not self.vision_enabled and self.vision and self.has_camera:
            self.vision.stop()
            self.has_camera = False
            self.last_frame_b64 = None
            # Re-init for potential re-enable
            self.vision = Vision()
        return self.vision_enabled

    def toggle_hearing(self) -> bool:
        self.hearing_enabled = not self.hearing_enabled
        return self.hearing_enabled

    def toggle_voice(self) -> bool:
        self.voice_enabled = not self.voice_enabled
        return self.voice_enabled

    def switch_voice_provider(self, provider: str) -> dict:
        """Hot-swap the voice provider without restarting."""
        if self.voice:
            self.voice.close()

        # Temporarily override the config
        cfg.TTS_PROVIDER = provider
        self.voice = Voice()
        self._add_log("system", f"Voice switched to {provider}")
        return self.get_voice_info()

    def get_voice_info(self) -> dict:
        """Return current voice provider info."""
        provider = "offline"
        if self.voice:
            provider = getattr(self.voice, "_provider", "unknown")
        return {
            "provider": provider,
            "providers": ["edge", "elevenlabs", "local"],
            "labels": {
                "edge": "Edge TTS (Free)",
                "elevenlabs": "ElevenLabs (Paid)",
                "local": "XTTS Clone (Local)",
            },
        }

    # ── Logging ──────────────────────────────────────────

    def _add_log(self, role: str, text: str):
        entry = {"role": role, "text": text, "time": time.time()}
        with self._log_lock:
            self._log.append(entry)
            # Keep last 200 entries
            if len(self._log) > 200:
                self._log = self._log[-200:]
        print(f"[{role.upper()}] {text}")

    def get_log(self, since: float = 0.0) -> list[dict]:
        with self._log_lock:
            if since:
                return [e for e in self._log if e["time"] > since]
            return list(self._log)

    def get_status(self) -> dict:
        provider = "offline"
        if self.voice:
            provider = getattr(self.voice, "_provider", "unknown")
        hearing_mode = "off"
        if self.hearing and self.hearing_enabled:
            hearing_mode = getattr(self.hearing, "mode", "always_listen")
        return {
            "running": self._running,
            "vision": self.vision_enabled,
            "hearing": self.hearing_enabled,
            "voice": self.voice_enabled,
            "has_camera": self.has_camera,
            "speaking": bool(self.voice and self.voice.is_speaking),
            "voice_provider": provider,
            "speech_id": self._speech_id,
            "hearing_mode": hearing_mode,
        }


# ── CLI entry point ──────────────────────────────────────

def startup_check():
    missing = cfg.validate()
    if missing:
        print("\n[HAL9000] Missing required environment variables:")
        for key in missing:
            print(f"  -> {key}")
        print("\nCopy .env.example to .env and fill in your keys.\n")
        sys.exit(1)


def main():
    """Standalone CLI mode (no web UI)."""
    startup_check()
    engine = HALEngine()
    engine.start()

    print("\n[HAL9000] Running. Press 'q' to quit.\n")

    try:
        while engine.running:
            if engine.has_camera and engine.vision:
                engine.vision.show_window()
                key = cv2.waitKey(100) & 0xFF
                if key == ord("q"):
                    break
            else:
                time.sleep(0.2)
    except KeyboardInterrupt:
        print("\n[HAL9000] Interrupted.")
    finally:
        engine.stop()
        print("[HAL9000] Shutdown complete.")


if __name__ == "__main__":
    main()
