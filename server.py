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

from flask import Flask, Response, jsonify, make_response, render_template, request

from config import cfg
from hal9000 import HALEngine, startup_check

app = Flask(__name__, static_folder="assets", static_url_path="/assets")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB max for audio uploads
engine = HALEngine()
engine.browser_audio = True  # Audio plays in browser when using web UI

# Wire engine reference into tools that need it (avoids circular imports)
from core.tools.artifacts import set_engine as _set_artifact_engine
from core.tools.delegation import set_engine as _set_delegation_engine
from core.tools.memory import set_engine as _set_memory_engine
_set_artifact_engine(engine)
_set_delegation_engine(engine)
_set_memory_engine(engine)


# ── Pages ────────────────────────────────────────────────

@app.route("/")
def index():
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ── API ──────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    return jsonify(engine.get_status())


@app.route("/api/license")
def api_license():
    try:
        from core.license import get_license
        lic = get_license()
        return jsonify({"tier": lic.tier, "valid": lic.valid, "expires": lic.expires})
    except ImportError:
        return jsonify({"tier": "free", "valid": False, "expires": ""})


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
        "voice": engine.toggle_voice,
    }
    fn = toggles.get(subsystem)
    if not fn:
        return jsonify({"error": f"Unknown subsystem: {subsystem}"}), 400
    fn()
    return jsonify(engine.get_status())


@app.route("/api/blur", methods=["POST"])
def api_blur():
    """Toggle background blur on webcam feed."""
    if engine.vision:
        engine.vision.blur_background = not engine.vision.blur_background
        return jsonify({"blur": engine.vision.blur_background})
    return jsonify({"error": "Vision not available"}), 400


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


@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    """Transcribe browser-recorded audio. Expects multipart file 'audio' (WAV)."""
    if not engine.running or not engine.hearing:
        return jsonify({"error": "HAL is not active"}), 503

    audio_file = request.files.get("audio")
    if not audio_file:
        return jsonify({"error": "No audio file"}), 400

    audio_bytes = audio_file.read()
    if len(audio_bytes) < 1000:
        return jsonify({"text": None, "error": "Audio too short"})

    text = engine.transcribe_audio(audio_bytes)
    return jsonify({"text": text})


@app.route("/api/voice_chat", methods=["POST"])
def api_voice_chat():
    """Record → transcribe → think → respond, all in one call. Legacy/CLI mode."""
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


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    """Streaming chat — returns SSE events with tokens as they arrive."""
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Empty message"}), 400
    if len(text) > 2000:
        return jsonify({"error": "Message too long"}), 413

    def generate():
        try:
            for event in engine.send_text_stream(text):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'done', 'text': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


# ── Background Tasks API ─────────────────────────────────

@app.route("/api/tasks")
def api_tasks():
    """List all background tasks with status."""
    return jsonify(engine.task_runner.list_tasks())


@app.route("/api/tasks", methods=["POST"])
def api_submit_task():
    """Submit a new background task."""
    data = request.get_json(silent=True) or {}
    desc = data.get("task", "").strip()
    if not desc:
        return jsonify({"error": "No task description"}), 400
    cwd = data.get("working_directory", "")
    task = engine.task_runner.submit(desc, cwd)
    return jsonify({"id": task.id, "status": task.status})


@app.route("/api/tasks/<task_id>/cancel", methods=["POST"])
def api_cancel_task(task_id):
    """Cancel a background task."""
    ok = engine.task_runner.cancel(task_id)
    return jsonify({"cancelled": ok})


# ── Artifacts API ─────────────────────────────────────────

@app.route("/api/artifacts")
def api_artifacts():
    """List all artifacts."""
    with engine._artifact_lock:
        return jsonify(list(engine._artifacts))


@app.route("/api/artifacts/<artifact_id>")
def api_artifact(artifact_id):
    """Get a single artifact by ID."""
    with engine._artifact_lock:
        for a in engine._artifacts:
            if a["id"] == artifact_id:
                return jsonify(a)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/artifacts/<artifact_id>", methods=["PUT"])
def api_update_artifact(artifact_id):
    """Update an artifact's content."""
    data = request.get_json(force=True)
    content = data.get("content", "")
    with engine._artifact_lock:
        for a in engine._artifacts:
            if a["id"] == artifact_id:
                a["content"] = content
                a["updated_at"] = __import__("time").time()
                engine._artifact_version += 1
                return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404


@app.route("/api/tools")
def api_tools():
    """List all registered tools with names and descriptions."""
    from core.tools import TOOL_REGISTRY
    tool_list = []
    for name, tdef in TOOL_REGISTRY.items():
        tool_list.append({
            "name": name,
            "description": tdef.description[:120],
            "safety": tdef.safety,
        })
    return jsonify({"tools": tool_list, "count": len(tool_list)})


@app.route("/api/run", methods=["POST"])
def api_run_code():
    """Execute code in a sandboxed subprocess. Returns stdout/stderr."""
    import subprocess as _sp

    data = request.get_json(force=True)
    code = data.get("code", "")
    language = data.get("language", "python").lower()

    if not code.strip():
        return jsonify({"error": "No code provided"})

    try:
        if language in ("python", "python3", "py"):
            result = _sp.run(
                ["python3", "-c", code],
                capture_output=True, text=True, timeout=10,
                cwd="/tmp",
                env={"PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"), "HOME": os.path.expanduser("~")}
            )
        elif language in ("javascript", "js", "node"):
            result = _sp.run(
                ["node", "-e", code],
                capture_output=True, text=True, timeout=10,
                cwd="/tmp",
                env={"PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"), "HOME": os.path.expanduser("~")}
            )
        elif language in ("bash", "sh", "shell"):
            result = _sp.run(
                ["bash", "-c", code],
                capture_output=True, text=True, timeout=10,
                cwd="/tmp",
                env={"PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"), "HOME": os.path.expanduser("~")}
            )
        else:
            return jsonify({"error": f"Unsupported language: {language}"})

        return jsonify({
            "stdout": result.stdout[:5000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
        })
    except _sp.TimeoutExpired:
        return jsonify({"error": "Execution timed out (10s limit)"})
    except FileNotFoundError:
        return jsonify({"error": f"Runtime not found for {language}"})
    except Exception as e:
        return jsonify({"error": str(e)[:500]})


# ── Open Claude Code (direct, no brain) ──────────────────

@app.route("/api/open_claude", methods=["POST"])
def api_open_claude():
    """Open Claude Code CLI in a new Terminal window — direct tool call, no LLM."""
    from core.tools import execute
    result = execute("open_claude_code", {})
    if "error" in result:
        return jsonify({"error": result["error"]})
    return jsonify({"ok": True, "result": result.get("result", "")})


# ── Send to Claude Code (open terminal with code) ────────

@app.route("/api/send_to_claude", methods=["POST"])
def api_send_to_claude():
    """Run Claude Code review as a background task, stream output to camera panel."""
    import tempfile

    data = request.get_json(force=True)
    code = data.get("code", "")
    language = data.get("language", "code")
    title = data.get("title", "artifact")

    if not code.strip():
        return jsonify({"error": "No code provided"})

    # Write code to a temp file so Claude Code can read it
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=f".{language}", prefix="hal_artifact_",
        dir="/tmp", delete=False
    )
    tmp.write(code)
    tmp.close()

    # Submit as a background task (streams output via SSE)
    task_desc = f"Review and improve the code in {tmp.name} — it is a {language} {title}. Read the file first, then suggest improvements."
    hal_dir = os.path.dirname(os.path.abspath(__file__))
    task = engine.task_runner.submit(task_desc, hal_dir)

    # Store the task ID for the camera panel viewer
    engine._claude_output_task = task.id

    return jsonify({"ok": True, "file": tmp.name, "task_id": task.id})


@app.route("/api/claude_output")
def api_claude_output():
    """Get the current Claude Code output for the camera panel viewer."""
    task_id = getattr(engine, "_claude_output_task", None)
    if not task_id:
        return jsonify({"active": False, "output": "", "status": "idle"})

    task = engine.task_runner.get_task(task_id)
    if not task:
        return jsonify({"active": False, "output": "", "status": "idle"})

    from dataclasses import asdict
    t = asdict(task)
    output = ""
    if t["status"] == "running":
        output = t["progress"] or "Starting Claude Code..."
    elif t["status"] == "completed":
        output = t["result"] or "(no output)"
    elif t["status"] == "failed":
        output = t["error"] or "Task failed"

    return jsonify({
        "active": t["status"] in ("running", "queued"),
        "output": output[:5000],
        "status": t["status"],
        "task_id": task_id,
    })


# ── Orchestrator API ──────────────────────────────────────

@app.route("/api/agents")
def api_agents():
    """List all orchestrated agents and their status."""
    return jsonify(engine.orchestrator.list_agents())


@app.route("/api/agents/conflicts")
def api_agent_conflicts():
    """Check for file conflicts between agents."""
    return jsonify(engine.orchestrator.check_conflicts())


@app.route("/api/agents/<agent_id>/cancel", methods=["POST"])
def api_cancel_agent(agent_id):
    """Cancel an agent."""
    ok = engine.orchestrator.cancel_agent(agent_id)
    return jsonify({"cancelled": ok})


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
                "tasks": engine.task_runner.list_tasks(),
                "artifact_version": engine._artifact_version,
                "agents": engine.orchestrator.list_agents(),
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
