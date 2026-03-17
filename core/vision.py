"""
HAL9000 — Vision
Webcam frame capture with face detection overlay.
Returns base64-encoded JPEG for LLM vision API.
Provides MJPEG stream with red face-tracking grid for the browser HUD.
"""

import base64
import io
import threading
import time
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from config import cfg


class Vision:
    def __init__(self):
        self.cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[bytes] = None  # clean frame for LLM
        self._latest_hud_frame: Optional[bytes] = None  # frame with HUD overlay
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Face detection
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._face_cascade = cv2.CascadeClassifier(cascade_path)
        self._last_faces = []  # smooth face tracking

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
        frame_count = 0
        while self._running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # Clean frame for LLM (no overlay)
                clean_bytes = self._encode(frame)

                # HUD frame with face tracking (run detection every 3 frames for perf)
                frame_count += 1
                if frame_count % 3 == 0:
                    self._detect_faces(frame)

                hud_frame = frame.copy()
                self._draw_face_tracking(hud_frame)
                hud_bytes = self._encode_raw(hud_frame)

                with self._lock:
                    self._latest_frame = clean_bytes
                    self._latest_hud_frame = hud_bytes

            time.sleep(0.05)

    def _detect_faces(self, frame):
        """Run Haar cascade face detection."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = self._face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(60, 60),
        )
        if len(faces) > 0:
            self._last_faces = faces
        # Fade out after 15 frames (~0.75s) of no detection
        elif hasattr(self, '_no_face_count'):
            self._no_face_count += 1
            if self._no_face_count > 15:
                self._last_faces = []
        else:
            self._no_face_count = 0

    def _draw_face_tracking(self, frame):
        """Draw red tracking grid overlay on detected faces."""
        h, w = frame.shape[:2]
        red = (0, 0, 255)  # BGR
        dim_red = (0, 0, 140)

        for (x, y, fw, fh) in self._last_faces:
            cx, cy = x + fw // 2, y + fh // 2

            # Main tracking rectangle
            cv2.rectangle(frame, (x, y), (x + fw, y + fh), red, 1)

            # Corner brackets (thicker)
            bracket_len = int(fw * 0.2)
            thickness = 2

            # Top-left
            cv2.line(frame, (x, y), (x + bracket_len, y), red, thickness)
            cv2.line(frame, (x, y), (x, y + bracket_len), red, thickness)
            # Top-right
            cv2.line(frame, (x + fw, y), (x + fw - bracket_len, y), red, thickness)
            cv2.line(frame, (x + fw, y), (x + fw, y + bracket_len), red, thickness)
            # Bottom-left
            cv2.line(frame, (x, y + fh), (x + bracket_len, y + fh), red, thickness)
            cv2.line(frame, (x, y + fh), (x, y + fh - bracket_len), red, thickness)
            # Bottom-right
            cv2.line(frame, (x + fw, y + fh), (x + fw - bracket_len, y + fh), red, thickness)
            cv2.line(frame, (x + fw, y + fh), (x + fw, y + fh - bracket_len), red, thickness)

            # Crosshair at center
            cross_size = 8
            cv2.line(frame, (cx - cross_size, cy), (cx + cross_size, cy), dim_red, 1)
            cv2.line(frame, (cx, cy - cross_size), (cx, cy + cross_size), dim_red, 1)

            # Small circle at center
            cv2.circle(frame, (cx, cy), 3, red, 1)

            # Label
            label = "TRACKING"
            cv2.putText(
                frame, label, (x, y - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, red, 1, cv2.LINE_AA,
            )

    def _encode(self, frame) -> bytes:
        """Resize and JPEG-encode a cv2 frame -> raw bytes (for LLM)."""
        h, w = frame.shape[:2]
        if w > 1024:
            scale = 1024 / w
            frame = cv2.resize(frame, (1024, int(h * scale)))

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        buf = io.BytesIO()
        pil.save(buf, format="JPEG", quality=80)
        return buf.getvalue()

    def _encode_raw(self, frame) -> bytes:
        """JPEG-encode a cv2 frame directly (for HUD stream)."""
        h, w = frame.shape[:2]
        if w > 1024:
            scale = 1024 / w
            frame = cv2.resize(frame, (1024, int(h * scale)))

        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ret else b""

    def get_frame_bytes(self) -> Optional[bytes]:
        """Return the latest HUD frame (with face tracking) as raw JPEG bytes."""
        with self._lock:
            return self._latest_hud_frame

    def get_frame_b64(self) -> Optional[str]:
        """Return the latest clean frame as a base64 string (for LLM)."""
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
