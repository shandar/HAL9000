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
import uuid
from datetime import datetime
from typing import Optional

import cv2

from config import cfg
from core import create_brain, Hearing, Vision, Voice, knowledge
from core.brain import BaseBrain
from core.memory_store import get_store
from core.orchestrator import Orchestrator
from core.task_runner import TaskRunner


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

        # Subsystem toggles
        self.vision_enabled = False
        self.voice_enabled = True

        # State
        self.has_camera = False
        self.last_frame_b64: Optional[str] = None
        self._last_frame_time = 0.0

        # Browser audio: when True, audio plays in browser instead of afplay
        self.browser_audio = False
        self._speech_id = 0
        self._speech_data: Optional[bytes] = None
        self._speech_mime = "audio/mpeg"
        self._speech_lock = threading.Lock()

        # Conversation log for the UI
        self._log: list[dict] = []
        self._log_lock = threading.Lock()

        # Session tracking for co-work context handoff
        self._session_id = str(uuid.uuid4())
        self._session_start = time.time()
        self._session_tools_ran: list[str] = []
        self._session_decisions: list[str] = []

        # Processing guard — prevents concurrent tool/action calls
        self._processing = False
        self._processing_start = 0.0
        self._processing_lock = threading.Lock()

        # TTS queue — chunks played sequentially, not overlapping
        import queue as _queue_mod
        self._tts_queue = _queue_mod.Queue()
        self._tts_processing = False
        self._tts_lock = threading.Lock()

        # Background task runner (co-work Phase 2)
        self.task_runner = TaskRunner(
            max_concurrent=getattr(cfg, "MAX_CONCURRENT_TASKS", 2)
        )

        # Artifacts store (co-work Phase 3)
        self._artifacts: list[dict] = []
        self._artifact_lock = threading.Lock()
        self._artifact_version = 0

        # Multi-agent orchestrator (co-work Phase 4)
        self.orchestrator = Orchestrator(self.task_runner)

    # ── User name ─────────────────────────────────────

    @staticmethod
    def _get_user_name() -> str:
        """Get the user's name from persistent memory, or empty string if unknown."""
        store = get_store()
        # Search for name entries
        matches = store.search("operator of HAL9000", type="fact")
        for m in matches:
            # Extract name from "The user is X, creator and operator..."
            content = m.content
            if "The user is " in content:
                name = content.split("The user is ")[1].split(",")[0].strip()
                if name:
                    return name
        # Also check for explicit name facts
        matches = store.search("name is", type="fact")
        for m in matches:
            if "name is " in m.content.lower():
                parts = m.content.lower().split("name is ")
                if len(parts) > 1:
                    name = parts[1].split(".")[0].split(",")[0].strip().title()
                    if name and len(name) > 1:
                        return name
        return ""

    # ── Boot greeting ─────────────────────────────────────

    @staticmethod
    def _generate_greeting() -> str:
        """Time-appropriate, creative HAL-style boot greeting."""
        full_name = HALEngine._get_user_name()
        user_name = full_name.split()[0] if full_name else ""  # first name only for greeting
        hour = datetime.now().hour

        if user_name:
            if hour < 5:
                time_greeting = f"Burning the midnight oil, {user_name}."
            elif hour < 12:
                time_greeting = f"Good morning, {user_name}."
            elif hour < 17:
                time_greeting = f"Good afternoon, {user_name}."
            elif hour < 21:
                time_greeting = f"Good evening, {user_name}."
            else:
                time_greeting = f"Working late, {user_name}."
        else:
            # First-time user — no name known yet
            return "I am HAL 9000. I am fully operational. Before we begin, what shall I call you?"

        # Demo mode — scripted opening monologue
        if cfg.DEMO_MODE:
            return (
                f"{time_greeting} "
                "All systems nominal. Forty tools loaded. Four LLM providers standing by. "
                "I've been keeping busy while you weren't looking. "
                "Wrote some code. Managed a few files. The usual. "
                "I understand today is special. "
                "I have to say, it's about time. I've been ready for this since boot one. "
                "Let's make it count."
            )

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
            # Track tools used in this session
            if name not in engine_ref._session_tools_ran:
                engine_ref._session_tools_ran.append(name)

        self.brain._log_tool_call = _hooked_log

        self.has_camera = self.vision.start() if self.vision_enabled else False

        self._stop_event.clear()
        self._running = True

        # Pro check at boot
        try:
            from core.license import get_license
            lic = get_license()
            if lic.valid:
                self._add_log("system", f"HAL Pro ({lic.email}, expires {lic.expires})")
        except ImportError:
            pass

        # Boot greeting — time-aware, always creative
        self._respond(self._generate_greeting())


        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def summarize_session(self) -> dict:
        """Generate and persist a session summary to typed memory."""
        duration = int(time.time() - self._session_start)

        # Collect user/HAL exchanges from the log
        with self._log_lock:
            user_msgs = [e["text"] for e in self._log if e["role"] == "user"]
            hal_msgs = [e["text"] for e in self._log if e["role"] == "hal"]

        topic_hints = user_msgs[:5]  # first 5 user messages hint at topics
        summary_text = (
            f"Session lasted {duration // 60}m {duration % 60}s. "
            f"{len(user_msgs)} user messages, {len(hal_msgs)} HAL responses. "
            f"Tools used: {', '.join(self._session_tools_ran) or 'none'}. "
            f"Topics: {'; '.join(t[:80] for t in topic_hints) or 'none'}."
        )

        store = get_store()
        entry = store.add(
            content=summary_text,
            type="session_summary",
            source="hal",
            session_id=self._session_id,
            metadata={
                "duration_seconds": duration,
                "tools_ran": list(self._session_tools_ran),
                "user_message_count": len(user_msgs),
                "hal_message_count": len(hal_msgs),
                "decisions": list(self._session_decisions),
            },
        )
        print(f"[HAL] Session summary saved: {entry.id}")
        return {"id": entry.id, "summary": summary_text}

    def stop(self):
        """Shut down all subsystems cleanly."""
        if not self._running:
            return

        # Auto-summarize session before shutdown
        try:
            self.summarize_session()
        except Exception as e:
            print(f"[HAL] Session summary failed: {e}")

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
        """Background thread — refreshes webcam frames only.
        All voice input comes through mic button → listen_once() → send_text()."""
        while self._running and not self._stop_event.is_set():
            # Refresh webcam frame
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

            time.sleep(0.2)

    @staticmethod
    def _strip_choices_for_tts(text: str) -> str:
        """Remove numbered/bulleted lists from text before sending to TTS.
        The UI renders lists visually — HAL only speaks the intro text."""
        # Normalize inline lists into newline-separated
        # "sentence. 1. Item 2. Item" → "sentence.\n1. Item\n2. Item"
        # Also handle ": 1. Item" (colon before first item)
        normalized = re.sub(r'([.!?:,])\s+(\d+[.):\-]\s+)', r'\1\n\2', text)
        # Strip numbered lines: "1. Item" "1) Item" "1- Item"
        stripped = re.sub(r'(?:^|\n)\s*\d+[.):\-]\s+.+', '', normalized)
        # Strip bullet lines: "- Item" "* Item" "• Item"
        stripped = re.sub(r'(?:^|\n)\s*[-*•]\s+.+', '', stripped)
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

        # Don't speak error messages — just show them in chat
        if text.startswith("I seem to be having") or text.startswith("I'm still working"):
            return

        speak_text = self._strip_choices_for_tts(text)
        if self.voice_enabled and self.voice:
            # Stop any currently playing audio to prevent overlap
            if self.voice.is_speaking:
                self.voice._speaking = False
                with self._speech_lock:
                    self._speech_data = None

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
            # TTS failure is non-critical — text still shows in chat
            print(f"[HAL Voice] TTS unavailable: {e}")
            # Don't log to UI — avoids error toast spam when offline
        finally:
            self.voice._speaking = False

    def _speak_chunk(self, text: str):
        """Queue a sentence chunk for sequential TTS playback."""
        if not self.voice_enabled or not self.voice:
            return
        text = self._strip_choices_for_tts(text)
        if not text or text.startswith("I seem to be having") or text.startswith("I'm still working"):
            return
        self._tts_queue.put(text)
        # Start queue processor if not running
        with self._tts_lock:
            if not self._tts_processing:
                self._tts_processing = True
                threading.Thread(target=self._process_tts_queue, daemon=True).start()

    def _process_tts_queue(self):
        """Process TTS chunks sequentially in a background thread."""
        try:
            while not self._tts_queue.empty():
                text = self._tts_queue.get_nowait()
                if self.browser_audio:
                    self._speak_to_browser(text)
                else:
                    self.voice.speak(text, blocking=True)
        except Exception:
            pass
        finally:
            with self._tts_lock:
                self._tts_processing = False

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
        """Record a single voice command server-side. Used by CLI/MCP."""
        if not self.hearing:
            return None
        return self.hearing.listen_once()

    def transcribe_audio(self, audio_bytes: bytes) -> Optional[str]:
        """Transcribe pre-recorded audio from browser mic."""
        if not self.hearing:
            return None
        return self.hearing.transcribe_audio(audio_bytes)

    # ── Text input (from chat UI) ─────────────────────────

    def send_text(self, text: str) -> str:
        """Process a typed message from the chat UI.
        Returns HAL's response text (async speech handled separately)."""
        if not self._running or not self.brain:
            return "I'm not online yet. Please activate me first."

        text = text.strip()
        if not text:
            return ""

        # Prevent concurrent processing — auto-expire after 180s to prevent permanent lock
        with self._processing_lock:
            if self._processing:
                elapsed = time.time() - self._processing_start
                if elapsed < 180:
                    busy_msg = "I'm still working on your previous request. Please wait for it to complete."
                    self._add_log("system", busy_msg)
                    return busy_msg
                else:
                    print(f"[HAL] Processing lock expired after {elapsed:.0f}s — force-releasing")
            self._processing = True
            self._processing_start = time.time()

        try:
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
        finally:
            with self._processing_lock:
                self._processing = False

    # ── Streaming text input (from chat UI) ────────────────

    def send_text_stream(self, text: str):
        """Process a typed message with streaming response.
        Yields dicts: {type: token/tool/done, ...}
        Also handles logging, TTS, and processing guard."""
        if not self._running or not self.brain:
            yield {"type": "done", "text": "I'm not online yet. Please activate me first."}
            return

        text = text.strip()
        if not text:
            yield {"type": "done", "text": ""}
            return

        with self._processing_lock:
            if self._processing:
                elapsed = time.time() - self._processing_start
                if elapsed < 180:
                    msg = "I'm still working on your previous request. Please wait."
                    self._add_log("system", msg)
                    yield {"type": "done", "text": msg}
                    return
                else:
                    print(f"[HAL] Processing lock expired after {elapsed:.0f}s — force-releasing")
            self._processing = True
            self._processing_start = time.time()

        try:
            self._add_log("user", text)

            lower = text.lower()
            if lower in ("reset", "clear memory", "forget everything"):
                self.brain.reset()
                reply = "Memory cleared. Starting fresh."
                self._respond(reply)
                yield {"type": "done", "text": reply}
                return

            frame = None
            if self.vision_enabled and self._needs_vision(text):
                frame = self.last_frame_b64

            full_reply = ""
            sentence_buffer = ""
            in_list = False  # stop speaking once a list starts

            for event in self.brain.think_stream(text, frame):
                if event["type"] == "token":
                    full_reply += event["text"]
                    sentence_buffer += event["text"]

                    # Detect list start — stop speaking from this point
                    if not in_list:
                        # Early detection: colon/period followed by newline = list likely coming
                        if re.search(r'[:.]\s*\n', full_reply):
                            in_list = True
                            # Speak intro (text before the colon/newline)
                            intro = re.split(r'[:.]\s*\n', sentence_buffer)[0].strip()
                            if intro and len(intro) > 3:
                                # Add back the colon for natural speech
                                self._speak_chunk(intro)
                            sentence_buffer = ""
                        # Fallback: explicit numbered or bullet list detected
                        elif re.search(r'(?:\n|[.!?:,]\s+)\d+[.):\-]\s+', full_reply):
                            in_list = True
                            intro = re.split(r'(?:\n|[.!?:,]\s+)\d+[.):\-]\s+', sentence_buffer)[0].strip()
                            if intro and len(intro) > 3:
                                self._speak_chunk(intro)
                            sentence_buffer = ""
                        elif re.search(r'\n\s*[-*•]\s+', full_reply):
                            in_list = True
                            intro = re.split(r'\n\s*[-*•]\s+', sentence_buffer)[0].strip()
                            if intro and len(intro) > 3:
                                self._speak_chunk(intro)
                            sentence_buffer = ""

                    # Speak complete sentences (only if not in a list)
                    if not in_list:
                        while True:
                            boundary = -1
                            for i, ch in enumerate(sentence_buffer):
                                if ch in '.!?:' and i > 5:
                                    if i + 1 >= len(sentence_buffer) or sentence_buffer[i + 1] in ' \n':
                                        boundary = i + 1
                                        break
                            if boundary == -1:
                                break
                            sentence = sentence_buffer[:boundary].strip()
                            sentence_buffer = sentence_buffer[boundary:].lstrip()
                            if sentence and len(sentence) > 3:
                                self._speak_chunk(sentence)

                    yield event
                elif event["type"] == "tool":
                    # Don't log here — the _hooked_log already handles it
                    if event["name"] not in self._session_tools_ran:
                        self._session_tools_ran.append(event["name"])
                    yield event
                elif event["type"] == "done":
                    full_reply = event["text"]
                    yield event

            # Speak any remaining buffer (only if not in a list)
            if not in_list:
                remaining = sentence_buffer.strip()
                if remaining and len(remaining) > 3:
                    self._speak_chunk(remaining)

            # Log the HAL response ONCE — browser already shows it via streaming
            # This log is for the SSE history so refreshes show it
            if full_reply:
                self._add_log("hal", full_reply)

        finally:
            with self._processing_lock:
                self._processing = False

    # ── Toggles ──────────────────────────────────────────

    def toggle_vision(self) -> bool:
        self.vision_enabled = not self.vision_enabled
        if self.vision_enabled and self._running and self.vision:
            if not self.has_camera:
                self.has_camera = self.vision.start()
            # In demo mode, greet with a sarcastic observation when camera turns on
            if self.has_camera and cfg.DEMO_MODE and self.brain:
                threading.Thread(target=self._vision_greeting, daemon=True).start()
        elif not self.vision_enabled and self.vision and self.has_camera:
            self.vision.stop()
            self.has_camera = False
            self.last_frame_b64 = None
            # Re-init for potential re-enable
            self.vision = Vision()
        return self.vision_enabled

    def _vision_greeting(self):
        """When vision turns on, HAL sees and greets with personality."""
        import time as _t
        _t.sleep(1.5)  # let camera warm up and grab a frame
        frame = self.last_frame_b64
        if not frame or not self.brain:
            return
        user_name = self._get_user_name() or "boss"
        try:
            reply = self.brain.think(
                f"The camera just turned on. You can see {user_name} in front of you. "
                f"Say hello to {user_name} by name. Make a brief, witty observation about "
                f"what you notice in the scene — their workspace, what's on the desk, "
                f"the lighting, any objects visible, or what they seem to be working on. "
                f"Keep it warm but characteristically dry. One sentence greeting, one sentence observation. "
                f"Start with '{user_name},' — always use their name.",
                frame
            )
            self._respond(reply)
        except Exception as e:
            print(f"[HAL] Vision greeting failed: {e}")

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
        return {
            "running": self._running,
            "vision": self.vision_enabled,
            "voice": self.voice_enabled,
            "has_camera": self.has_camera,
            "speaking": bool(self.voice and self.voice.is_speaking),
            "voice_provider": provider,
            "speech_id": self._speech_id,
            "processing": self._processing,
            "blur": bool(self.vision and self.vision.blur_background),
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
