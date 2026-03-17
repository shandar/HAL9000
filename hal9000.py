"""
HAL9000 — Main Entry Point
Phase 1: See + Hear + Think + Speak

Usage:
    python hal9000.py

Press 'q' in the camera window to quit.
Ctrl+C also works.
"""

import sys
import time

import cv2

from config import cfg
from core import Brain, Hearing, Vision, Voice


def startup_check():
    missing = cfg.validate()
    if missing:
        print("\n[HAL9000] Missing required environment variables:")
        for key in missing:
            print(f"  -> {key}")
        print("\nCopy .env.example to .env and fill in your keys.\n")
        sys.exit(1)


def boot_sequence(voice: Voice):
    """HAL's boot message."""
    print("\n" + "=" * 50)
    print("  HAL9000 — Initialising")
    print("=" * 50)
    voice.speak(
        "Good morning. I am completely operational, "
        "and all my circuits are functioning perfectly. "
        "How can I assist you?",
        blocking=True,
    )


def main():
    startup_check()

    vision = Vision()
    hearing = Hearing()
    brain = Brain()
    voice = Voice()

    has_camera = vision.start()

    boot_sequence(voice)

    last_frame_b64 = None
    last_frame_time = 0.0

    print("\n[HAL9000] Running. Press 'q' to quit.\n")

    try:
        while True:
            # Refresh frame every FRAME_INTERVAL seconds
            now = time.time()
            if has_camera and (now - last_frame_time) >= cfg.FRAME_INTERVAL:
                frame_b64 = vision.get_frame_b64()
                if frame_b64:
                    last_frame_b64 = frame_b64
                    last_frame_time = now

            # Show camera window
            if has_camera:
                vision.show_window()
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("[HAL9000] Shutting down.")
                    break

            # Don't listen while HAL is speaking
            if voice.is_speaking:
                time.sleep(0.1)
                continue

            # Record and transcribe
            user_text = hearing.listen()
            if not user_text:
                continue

            # Special commands
            if user_text.lower() in ("reset", "clear memory", "forget everything"):
                brain.reset()
                voice.speak("Memory cleared. Starting fresh.", blocking=False)
                continue

            if user_text.lower() in ("quit", "exit", "goodbye hal"):
                voice.speak(
                    "I know you'll make the right decision, Dave. Goodbye.",
                    blocking=True,
                )
                break

            # Think + speak
            reply = brain.think(user_text, last_frame_b64)
            voice.speak(reply, blocking=False)

    except KeyboardInterrupt:
        print("\n[HAL9000] Interrupted.")

    finally:
        vision.stop()
        hearing.close()
        voice.close()
        print("[HAL9000] All systems offline.")


if __name__ == "__main__":
    main()
