"""
HAL9000 — Vision
Webcam frame capture. Returns base64-encoded JPEG for Claude vision API.
"""

import base64
import io
import threading
import time
from typing import Optional

import cv2
from PIL import Image

from config import cfg


class Vision:
    def __init__(self):
        self.cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[bytes] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> bool:
        """Open webcam and begin background frame capture."""
        self.cap = cv2.VideoCapture(cfg.CAMERA_INDEX)
        if not self.cap.isOpened():
            print("[HAL Vision] No camera found — running without vision.")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        print(f"[HAL Vision] Camera started (index {cfg.CAMERA_INDEX})")
        return True

    def _capture_loop(self):
        """Background thread: continuously grab frames."""
        while self._running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                with self._lock:
                    self._latest_frame = self._encode(frame)
            time.sleep(0.05)  # grab at ~20fps, encode lazily

    def _encode(self, frame) -> bytes:
        """Resize and JPEG-encode a cv2 frame -> raw bytes."""
        h, w = frame.shape[:2]
        if w > 1024:
            scale = 1024 / w
            frame = cv2.resize(frame, (1024, int(h * scale)))

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        buf = io.BytesIO()
        pil.save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    def get_frame_b64(self) -> Optional[str]:
        """Return the latest frame as a base64 string, or None."""
        with self._lock:
            if self._latest_frame is None:
                return None
            return base64.standard_b64encode(self._latest_frame).decode("utf-8")

    def show_window(self):
        """Display the webcam feed in an OpenCV window. Call from main thread."""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                cv2.putText(
                    frame, "HAL9000", (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 200), 2
                )
                cv2.imshow("HAL9000 - Eye", frame)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()
        print("[HAL Vision] Camera stopped.")
