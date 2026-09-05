#!/usr/bin/env python3
"""
server/api/terminal.py — 内置终端（xterm.js + PTY，对齐 DSH Web UI 内置终端）

WebSocket `/api/v1/terminal/ws`：连接即 fork 一个交互式 shell（$SHELL 或 /bin/bash），
PTY 主端双向桥接 WebSocket；控制帧以 `\\x01` 前缀承载 JSON（resize 窗口尺寸）。
仅本机 127.0.0.1 监听，操作者自有 shell，非模型工具（模型仍走受限 shell_run）。
"""

from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import pty
import struct
import subprocess
import termios

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger("eco.server.terminal")

router = APIRouter()

SHELL = os.environ.get("SHELL", "/bin/bash")
DEFAULT_COLS = 120
DEFAULT_ROWS = 30


@router.websocket("/terminal/ws")
async def terminal_ws(ws: WebSocket) -> None:
    await ws.accept()
    try:
        master_fd, slave_fd = pty.openpty()
    except OSError as e:
        # 受限环境（沙箱/无 PTY 权限）优雅降级：告知前端而非崩溃
        await ws.send_text(f"\r\n[terminal] PTY 不可用: {e}\r\n")
        await ws.close()
        return
    _resize_pty(master_fd, DEFAULT_ROWS, DEFAULT_COLS)
    cwd = os.environ.get("ECO_WORKSPACE_DIR") or os.path.expanduser("~")
    proc = subprocess.Popen(
        [SHELL],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        preexec_fn=os.setsid,
        env=os.environ.copy(),
        cwd=cwd,
        close_fds=True,
    )
    os.close(slave_fd)
    loop = asyncio.get_running_loop()
    closed = False

    async def _send(data: bytes) -> None:
        try:
            await ws.send_bytes(data)
        except Exception:  # noqa: BLE001 — 连接已关，忽略
            pass

    def _read_pty() -> None:
        nonlocal closed
        try:
            while not closed:
                data = os.read(master_fd, 65536)
                if not data:
                    break
                fut = asyncio.run_coroutine_threadsafe(_send(data), loop)
                fut.add_done_callback(lambda f: f.exception() if not f.cancelled() else None)
        except OSError:
            pass

    reader = asyncio.to_thread(_read_pty)
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                data = msg["bytes"]
            else:
                data = (msg.get("text") or "").encode("utf-8", "replace")
            if data.startswith(b"\x01"):  # 控制帧：JSON resize
                try:
                    ctl = json.loads(data[1:].decode("utf-8", "replace"))
                    _resize_pty(master_fd, int(ctl.get("rows", DEFAULT_ROWS)), int(ctl.get("cols", DEFAULT_COLS)))
                except Exception:  # noqa: BLE001
                    pass
            else:
                os.write(master_fd, data)
    except WebSocketDisconnect:
        pass
    finally:
        closed = True
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        try:
            os.close(master_fd)
        except OSError:
            pass
        try:
            await reader
        except Exception:  # noqa: BLE001
            pass


def _resize_pty(fd: int, rows: int, cols: int) -> None:
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))
    except Exception:  # noqa: BLE001
        pass
