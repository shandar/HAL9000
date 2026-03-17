"""
HAL9000 — Web Control Server
Flask app serving the dashboard UI and API endpoints.

Usage:
    python server.py
    Open http://localhost:9000
"""

import json
import os
import time

from flask import Flask, Response, jsonify, render_template, request

from config import cfg
from hal9000 import HALEngine, startup_check

app = Flask(__name__, static_folder="assets", static_url_path="/assets")
engine = HALEngine()
engine.browser_audio = True  # Audio plays in browser when using web UI


# ── Pages ────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── API ──────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    return jsonify(engine.get_status())


@app.route("/api/start", methods=["POST"])
def api_start():
    if not engine.running:
        engine.start()
    return jsonify(engine.get_status())


@app.route("/api/stop", methods=["POST"])
def api_stop():
    if engine.running:
        engine.stop()
    return jsonify(engine.get_status())


@app.route("/api/toggle/<subsystem>", methods=["POST"])
def api_toggle(subsystem: str):
    toggles = {
        "vision": engine.toggle_vision,
        "hearing": engine.toggle_hearing,
        "voice": engine.toggle_voice,
    }
    fn = toggles.get(subsystem)
    if not fn:
        return jsonify({"error": f"Unknown subsystem: {subsystem}"}), 400
    fn()
    return jsonify(engine.get_status())


@app.route("/api/voice_provider", methods=["GET", "POST"])
def api_voice_provider():
    """Get or switch the active voice provider."""
    if request.method == "POST":
        provider = request.json.get("provider", "").lower()
        if provider not in ("edge", "elevenlabs", "local"):
            return jsonify({"error": "Unknown provider. Use: edge, elevenlabs, local"}), 400
        result = engine.switch_voice_provider(provider)
        return jsonify(result)
    else:
        return jsonify(engine.get_voice_info())


@app.route("/api/speech")
def api_speech():
    """Serve the latest synthesized speech audio for browser playback."""
    # Enable browser audio mode on first request
    engine.browser_audio = True
    data, mime, sid = engine.get_speech()
    if not data:
        return Response(status=204)
    return Response(data, mimetype=mime, headers={
        "Cache-Control": "no-cache",
        "X-Speech-Id": str(sid),
    })


@app.route("/api/speech_done", methods=["POST"])
def api_speech_done():
    """Browser signals that audio playback has finished."""
    engine.speech_done()
    return jsonify({"ok": True})


@app.route("/api/voice_chat", methods=["POST"])
def api_voice_chat():
    """Record → transcribe → think → respond, all in one call. No wake word."""
    if not engine.running or not engine.hearing:
        return jsonify({"error": "HAL is not active"}), 503

    import threading

    result = {"reply": "", "heard": ""}
    error = {"msg": ""}

    def _process():
        try:
            text = engine.listen_once()
            if not text:
                return
            result["heard"] = text
            result["reply"] = engine.send_text(text)
        except Exception as e:
            error["msg"] = str(e)

    t = threading.Thread(target=_process)
    t.start()
    t.join(timeout=30)

    if error["msg"]:
        return jsonify({"error": error["msg"]}), 500
    if not result["heard"]:
        return jsonify({"heard": None, "error": "Nothing heard — try again"})
    return jsonify({"heard": result["heard"], "reply": result["reply"]})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Accept typed text from the chat UI, process through brain, return reply."""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Empty message"}), 400
    if len(text) > 2000:
        return jsonify({"error": "Message too long (max 2000 chars)"}), 413

    # Run in a thread to avoid blocking (brain.think can take a few seconds)
    import threading

    result = {"reply": ""}
    error = {"msg": ""}

    def _process():
        try:
            result["reply"] = engine.send_text(text)
        except Exception as e:
            error["msg"] = str(e)

    t = threading.Thread(target=_process)
    t.start()
    t.join(timeout=60)

    if error["msg"]:
        return jsonify({"error": error["msg"]}), 500
    return jsonify({"reply": result["reply"]})


@app.route("/api/frame")
def api_frame():
    """Return a single webcam frame as base64 JPEG for MCP/API consumers."""
    if not engine.running or not engine.vision_enabled or not engine.vision:
        return jsonify({"error": "Vision not active"}), 503
    frame_b64 = engine.vision.get_frame_b64()
    if not frame_b64:
        return jsonify({"error": "No frame available"}), 503
    return jsonify({"frame": frame_b64})


@app.route("/api/log")
def api_log():
    try:
        since = float(request.args.get("since", 0))
    except (ValueError, TypeError):
        since = 0.0
    return jsonify(engine.get_log(since))


# ── Video stream (MJPEG) ─────────────────────────────────

@app.route("/api/video")
def api_video():
    """MJPEG stream of the webcam feed for the browser HUD."""

    def generate():
        while True:
            if engine.running and engine.vision_enabled and engine.vision:
                frame = engine.vision.get_frame_bytes()
                if frame:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + frame
                        + b"\r\n"
                    )
            time.sleep(0.05)  # ~20fps

    return Response(
        generate(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache"},
    )


# ── SSE stream ───────────────────────────────────────────

@app.route("/api/stream")
def api_stream():
    """Server-Sent Events: pushes status + new log entries every second."""

    def generate():
        last_log_time = 0.0
        while True:
            status = engine.get_status()
            new_entries = engine.get_log(since=last_log_time)
            if new_entries:
                last_log_time = new_entries[-1]["time"]

            payload = json.dumps({
                "status": status,
                "log": new_entries,
            })
            yield f"data: {payload}\n\n"
            time.sleep(1)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Main ─────────────────────────────────────────────────

if __name__ == "__main__":
    startup_check()
    print(f"\n  HAL9000 Control Panel → http://localhost:{cfg.SERVER_PORT}\n")
    host = os.environ.get("HAL_HOST", "127.0.0.1")
    app.run(
        host=host,
        port=cfg.SERVER_PORT,
        debug=False,
        threaded=True,
    )
