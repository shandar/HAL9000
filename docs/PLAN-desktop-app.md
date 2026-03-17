# PLAN: HAL 9000 Desktop App

**Status:** 📋 Proposed
**Priority:** Medium (Phase 1 enhancement)
**Effort:** Medium (2-3 sessions)

---

## Problem

HAL runs as two disconnected pieces: `python server.py` in a terminal + a browser tab at `localhost:9000`. This creates friction:

1. Users must manage two processes (terminal + browser)
2. No dock icon, no menu bar presence
3. No native camera/mic permission dialogs (browser handles it, but inconsistently)
4. Closing the browser tab doesn't stop HAL
5. Can't distribute to non-technical users

## Goal

Package HAL as a native macOS desktop app that launches with a double-click, shows a proper window with the dashboard, and manages the Python backend automatically.

---

## Approach: PyWebView + py2app

### Why PyWebView

| Factor | PyWebView | Electron |
|--------|-----------|----------|
| Runtime overhead | ~5MB (uses system WebKit) | ~200MB (bundles Chromium) |
| Language | Pure Python | Node.js + Python sidecar |
| Backend integration | Same process — Flask runs in-thread | Subprocess management + IPC |
| macOS native feel | WebKit matches Safari behavior | Chromium, different rendering |
| Implementation effort | ~100 lines of glue code | ~1000+ lines of config/bridge |
| Auto-update | Manual or Sparkle | electron-updater built-in |
| Cross-platform | macOS, Windows, Linux | macOS, Windows, Linux |

PyWebView is the right choice because HAL is Python-first. No language boundary to cross.

### Architecture

```
┌─────────────────────────────────────────┐
│           HAL 9000.app (macOS)          │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │         PyWebView Window          │  │
│  │    (native WebKit, no Chromium)   │  │
│  │                                   │  │
│  │    Points to localhost:9000       │  │
│  │    Full dashboard + chat UI       │  │
│  │    Native title bar + controls    │  │
│  └───────────────┬───────────────────┘  │
│                  │                       │
│  ┌───────────────▼───────────────────┐  │
│  │      Flask Server (in-thread)     │  │
│  │      localhost:9000               │  │
│  │                                   │  │
│  │  HALEngine → Brain → Tools        │  │
│  │  Vision → Hearing → Voice         │  │
│  │  All existing functionality       │  │
│  └───────────────────────────────────┘  │
│                                         │
│  Menu Bar: HAL 9000 | File | View       │
│  Dock Icon: HAL eye logo                │
│  System Tray: Optional mini-status      │
└─────────────────────────────────────────┘
```

---

## Implementation Steps

### Step 1: Create `desktop.py` — PyWebView launcher

**File:** `desktop.py` (new, ~80 lines)

```python
"""
HAL 9000 Desktop App — PyWebView launcher.
Starts Flask server in a background thread, opens native window.
"""

import sys
import threading
import time
import webview
from server import app, cfg

def start_server():
    """Run Flask in a daemon thread."""
    app.run(
        host="127.0.0.1",
        port=cfg.SERVER_PORT,
        debug=False,
        threaded=True,
        use_reloader=False,  # Important: no reloader in desktop mode
    )

def main():
    # Start Flask server in background
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    import urllib.request
    for _ in range(50):  # 5 second timeout
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{cfg.SERVER_PORT}/api/status")
            break
        except Exception:
            time.sleep(0.1)

    # Create native window
    window = webview.create_window(
        title="HAL 9000",
        url=f"http://127.0.0.1:{cfg.SERVER_PORT}",
        width=1400,
        height=900,
        min_size=(1024, 700),
        resizable=True,
        frameless=False,
        easy_drag=False,
        text_select=True,
    )

    # Start the GUI event loop (blocks until window closes)
    webview.start(
        debug=False,
        gui="cocoa",  # Use native macOS WebKit
    )

    # Window closed — exit cleanly
    sys.exit(0)

if __name__ == "__main__":
    main()
```

**Verification:** `python desktop.py` opens a native window with the full dashboard.

### Step 2: Add dependencies

**File:** `requirements.txt` (append)

```
pywebview>=5.0
```

For macOS native WebKit backend, pywebview uses PyObjC (already available on macOS).

### Step 3: Create macOS `.app` bundle with py2app

**File:** `setup_app.py` (new)

```python
from setuptools import setup

APP = ["desktop.py"]
DATA_FILES = [
    ("templates", ["templates/index.html"]),
    ("assets", [
        "assets/HAL.png",
        "assets/manifest.json",
        "assets/sw.js",
    ]),
    ("knowledge", []),  # Empty dir, user adds files
    ("memory", []),     # Created at runtime
]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/HAL.icns",  # Need to create this
    "plist": {
        "CFBundleName": "HAL 9000",
        "CFBundleDisplayName": "HAL 9000",
        "CFBundleIdentifier": "com.hal9000.desktop",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0",
        "NSCameraUsageDescription": "HAL 9000 uses the camera for vision capabilities.",
        "NSMicrophoneUsageDescription": "HAL 9000 uses the microphone for voice interaction.",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    },
    "packages": [
        "flask", "openai", "anthropic", "cv2", "pyaudio",
        "webview", "edge_tts", "duckduckgo_search",
    ],
    "includes": [
        "core", "core.brain", "core.vision", "core.hearing",
        "core.voice", "core.tools", "core.knowledge",
        "config", "hal9000", "server",
    ],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
```

**Build command:**
```bash
python setup_app.py py2app
```

**Output:** `dist/HAL 9000.app` — double-click to launch.

### Step 4: Create app icon

**File:** `assets/HAL.icns` (convert from HAL.png)

```bash
# Create icon set from existing HAL.png
mkdir -p HAL.iconset
sips -z 16 16     assets/HAL.png --out HAL.iconset/icon_16x16.png
sips -z 32 32     assets/HAL.png --out HAL.iconset/icon_16x16@2x.png
sips -z 32 32     assets/HAL.png --out HAL.iconset/icon_32x32.png
sips -z 64 64     assets/HAL.png --out HAL.iconset/icon_32x32@2x.png
sips -z 128 128   assets/HAL.png --out HAL.iconset/icon_128x128.png
sips -z 256 256   assets/HAL.png --out HAL.iconset/icon_128x128@2x.png
sips -z 256 256   assets/HAL.png --out HAL.iconset/icon_256x256.png
sips -z 512 512   assets/HAL.png --out HAL.iconset/icon_256x256@2x.png
sips -z 512 512   assets/HAL.png --out HAL.iconset/icon_512x512.png
sips -z 1024 1024 assets/HAL.png --out HAL.iconset/icon_512x512@2x.png
iconutil -c icns HAL.iconset -o assets/HAL.icns
rm -rf HAL.iconset
```

### Step 5: Adapt `server.py` for desktop mode

**File:** `server.py` (minor changes)

Add a `DESKTOP_MODE` flag so the server knows it's running inside a native window:

```python
# At top of server.py
DESKTOP_MODE = os.environ.get("HAL_DESKTOP", "0") == "1"
```

Changes when `DESKTOP_MODE=True`:
- Skip "Open in browser" print message
- Don't call `webbrowser.open()` (if ever added)
- Suppress Flask startup banner
- Bind only to 127.0.0.1 (already default)

### Step 6: Native macOS menu bar (optional enhancement)

PyWebView supports custom menus on macOS:

```python
menu_items = [
    webview.menu.Menu("HAL 9000", [
        webview.menu.MenuAction("About HAL 9000", show_about),
        webview.menu.MenuSeparator(),
        webview.menu.MenuAction("Preferences...", show_preferences),
    ]),
    webview.menu.Menu("View", [
        webview.menu.MenuAction("Toggle Fullscreen", toggle_fullscreen),
        webview.menu.MenuAction("Zoom In", zoom_in),
        webview.menu.MenuAction("Zoom Out", zoom_out),
    ]),
]
webview.start(menu=menu_items)
```

---

## Verification Steps

| # | Test | Expected |
|---|------|----------|
| 1 | `pip install pywebview` + `python desktop.py` | Native window opens with full dashboard |
| 2 | Click Activate in desktop window | HAL starts, all subsystems functional |
| 3 | Type in chat, send message | Brain responds, voice plays through window |
| 4 | Webcam feed visible | MJPEG stream renders in native WebKit |
| 5 | Close window | Process exits cleanly (no orphan Flask) |
| 6 | `python setup_app.py py2app` | Builds `dist/HAL 9000.app` bundle |
| 7 | Double-click `HAL 9000.app` | App launches, camera permission dialog appears |
| 8 | MCP server still works alongside desktop app | `claude mcp add` connects normally |

---

## File Changes Summary

| File | Action | Lines |
|------|--------|-------|
| `desktop.py` | **New** | ~80 |
| `setup_app.py` | **New** | ~50 |
| `requirements.txt` | **Modify** | +1 line |
| `server.py` | **Modify** | +5 lines (DESKTOP_MODE flag) |
| `assets/HAL.icns` | **New** | Generated from HAL.png |

**Total new code:** ~130 lines + icon generation script

---

## Future: Electron Upgrade Path

If we later need features PyWebView can't provide (auto-update, Windows installer, native notifications API), we can wrap HAL in Electron:

```
electron-app/
├── main.js          # Electron main process
├── preload.js       # Security bridge
├── package.json
└── python/          # Bundled Python + HAL (via pyinstaller)
```

Electron would spawn the Python backend as a child process and communicate via the existing REST API. The dashboard HTML would load directly (no localhost needed). This is ~10x more work but provides a more polished distribution story.

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| PyWebView WebKit doesn't support all CSS | Test dashboard rendering — WebKit is Safari-equivalent, should be fine |
| Camera/mic permissions in app bundle | `NSCameraUsageDescription` and `NSMicrophoneUsageDescription` in plist |
| py2app fails to bundle OpenCV/PyAudio | These have native C extensions — may need `--semi-standalone` or conda packaging |
| Large app bundle size (~500MB+) | Acceptable for v1. Optimize later with tree-shaking unused packages |
| Port 9000 already in use | Add port conflict detection in `desktop.py` with fallback |

---

## Decision Needed

**Option A:** Implement PyWebView desktop app now (2-3 sessions, ~130 lines)
**Option B:** Skip desktop, continue with Wake Word Detection (roadmap 1.1)
**Option C:** Do both — PyWebView is small enough to do first, then wake word

Recommendation: **Option C** — PyWebView is a quick win that dramatically improves the user experience, then we tackle wake word detection.
