"""
HAL9000 — Embedded Terminal WebSocket Server
Runs a PTY-backed terminal accessible via WebSocket on port 9001.
xterm.js in the browser connects to ws://localhost:9001 for full
interactive terminal access (shell or Claude Code CLI).

Runs in a background thread — does not interfere with Flask on port 9000.
"""

import asyncio
import os
import platform as _plat
import signal
import threading
from typing import Optional

# Unix-only imports — guarded for Windows compatibility
_UNIX = _plat.system() != "Windows"
if _UNIX:
    import fcntl
    import pty
    import select
    import struct
    import termios

import websockets
from websockets.asyncio.server import serve

# Active terminal state
_master_fd: Optional[int] = None
_child_pid: Optional[int] = None
_ws_connections: set = set()
_loop: Optional[asyncio.AbstractEventLoop] = None
_respawn_lock = asyncio.Lock()  # prevent concurrent respawn race

WS_PORT = int(os.environ.get("HAL_TERMINAL_PORT", "9001"))
# Origin whitelist for WebSocket security
_ALLOWED_ORIGINS = {"http://localhost:9000", "http://127.0.0.1:9000", "https://localhost:9000"}


def _spawn_shell(cmd: str = "/bin/bash") -> tuple[int, int]:
    """Fork a PTY and exec a shell. Returns (master_fd, child_pid)."""
    pid, fd = pty.fork()
    if pid == 0:
        # Child process — exec the shell
        os.execvp(cmd, [cmd, "--login"])
    else:
        # Parent — set master fd to non-blocking
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        # Set initial terminal size (120x30)
        _set_pty_size(fd, 120, 30)
        return fd, pid


def _set_pty_size(fd: int, cols: int, rows: int):
    """Set the PTY window size."""
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)
    except Exception:
        pass


async def _terminal_handler(websocket):
    """Handle a single xterm.js WebSocket connection."""
    global _master_fd, _child_pid

    # Security: check origin header to prevent cross-site WebSocket hijacking
    origin = websocket.request.headers.get("Origin", "")
    if origin and origin not in _ALLOWED_ORIGINS:
        await websocket.close(1008, "Origin not allowed")
        return

    _ws_connections.add(websocket)

    # Spawn shell if not already running (or if previous one died)
    if _master_fd is None or _child_pid is None:
        try:
            _master_fd, _child_pid = _spawn_shell()
        except Exception as e:
            await websocket.send(f"\r\n[HAL Terminal] Failed to start shell: {e}\r\n")
            _ws_connections.discard(websocket)
            return

    # Start PTY reader task
    reader_task = asyncio.create_task(_read_pty(websocket))

    try:
        async for message in websocket:
            if isinstance(message, str):
                # Check for resize messages: \x1b[8;rows;colst
                if message.startswith("\x1b[8;"):
                    try:
                        parts = message[4:-1].split(";")
                        rows, cols = int(parts[0]), int(parts[1])
                        if _master_fd is not None:
                            _set_pty_size(_master_fd, cols, rows)
                    except (ValueError, IndexError):
                        pass
                    continue

                # Write user input to PTY
                if _master_fd is not None:
                    try:
                        os.write(_master_fd, message.encode("utf-8"))
                    except OSError:
                        # PTY died — respawn
                        await _respawn_shell(websocket)
            elif isinstance(message, bytes):
                if _master_fd is not None:
                    try:
                        os.write(_master_fd, message)
                    except OSError:
                        await _respawn_shell(websocket)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        reader_task.cancel()
        _ws_connections.discard(websocket)

        # Reap PTY when all connections disconnect
        if not _ws_connections and _child_pid is not None:
            _cleanup_pty()


def _cleanup_pty():
    """Kill and clean up the PTY child process."""
    global _master_fd, _child_pid
    if _child_pid is not None:
        try:
            os.kill(_child_pid, signal.SIGTERM)
            os.waitpid(_child_pid, os.WNOHANG)
        except (OSError, ChildProcessError):
            pass
    if _master_fd is not None:
        try:
            os.close(_master_fd)
        except OSError:
            pass
    _master_fd = None
    _child_pid = None


async def _read_pty(websocket):
    """Read PTY output and send to WebSocket."""
    global _master_fd, _child_pid

    while True:
        if _master_fd is None:
            await asyncio.sleep(0.1)
            continue

        try:
            # Use select with timeout to avoid busy-waiting
            r, _, _ = select.select([_master_fd], [], [], 0.05)
            if r:
                data = os.read(_master_fd, 4096)
                if data:
                    # Send to all connected clients
                    for ws in list(_ws_connections):
                        try:
                            await ws.send(data.decode("utf-8", errors="replace"))
                        except Exception:
                            _ws_connections.discard(ws)
                else:
                    # EOF — shell exited
                    await _respawn_shell(websocket)
            else:
                await asyncio.sleep(0.02)
        except (OSError, ValueError):
            # PTY fd is invalid — shell died
            await asyncio.sleep(0.5)
            if _master_fd is not None:
                await _respawn_shell(websocket)


async def _respawn_shell(websocket):
    """Respawn the shell after it exits. Locked to prevent concurrent respawns."""
    global _master_fd, _child_pid

    async with _respawn_lock:
        # Clean up old PTY
        if _master_fd is not None:
            try:
                os.close(_master_fd)
            except OSError:
                pass
        if _child_pid is not None:
            try:
                os.waitpid(_child_pid, os.WNOHANG)
            except ChildProcessError:
                pass

        _master_fd = None
        _child_pid = None

        try:
            await websocket.send("\r\n[HAL Terminal] Shell exited. Restarting...\r\n")
        except Exception:
            pass

        await asyncio.sleep(0.5)

    try:
        _master_fd, _child_pid = _spawn_shell()
    except Exception as e:
        try:
            await websocket.send(f"\r\n[HAL Terminal] Failed to restart: {e}\r\n")
        except Exception:
            pass


async def _run_server():
    """Start the WebSocket server."""
    async with serve(_terminal_handler, "127.0.0.1", WS_PORT):
        print(f"[HAL Terminal] WebSocket server on ws://localhost:{WS_PORT}")
        await asyncio.Future()  # run forever


def start_terminal_server():
    """Start the terminal WebSocket server in a background thread.
    Only available on Unix (macOS/Linux) — PTY not supported on Windows."""
    global _loop

    if not _UNIX:
        print("[HAL Terminal] Embedded terminal not available on Windows (no PTY support)")
        return None

    def _thread_target():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        try:
            _loop.run_until_complete(_run_server())
        except Exception as e:
            print(f"[HAL Terminal] Server error: {e}")

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()
    return thread


def stop_terminal_server():
    """Stop the terminal server and clean up."""
    global _master_fd, _child_pid, _loop

    if _child_pid is not None:
        try:
            os.kill(_child_pid, signal.SIGTERM)
            os.waitpid(_child_pid, 0)
        except (OSError, ChildProcessError):
            pass

    if _master_fd is not None:
        try:
            os.close(_master_fd)
        except OSError:
            pass

    _master_fd = None
    _child_pid = None

    if _loop is not None:
        _loop.call_soon_threadsafe(_loop.stop)
