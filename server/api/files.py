#!/usr/bin/env python3
"""
server/api/files.py — 附件上传 / 语音转写 API
================================================
Web GUI 输入栏（DSH 对齐）后端：

- POST /files            本地文件上传 → 工作区 uploads/（模型可用 file_read 读取分析）
- POST /voice/transcribe 语音上传 → 飞书妙记转写（lark-cli: drive 上传 → minutes 生成 → 逐字稿）

安全：文件名清洗去路径、大小上限、落在 ECO_WORKSPACE_DIR/uploads 内；
语音转写走 lark-cli（本地已认证），webm/opus 先经 ffmpeg 转 m4a（妙记支持格式）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

logger = logging.getLogger("eco.server.files")

router = APIRouter()

MAX_BYTES = 300 * 1024 * 1024  # 附件上限 300MB
AUDIO_MAX_BYTES = 25 * 1024 * 1024  # 语音上限 25MB
MIN_AUDIO_BYTES = 2 * 1024  # 低于 2KB 视为无效录音
VOICE_TIMEOUT = 240  # 转写总超时（秒），妙记生成异步，需耐心
LARK_MINUTES_AUDIO = (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".wma", ".amr")


def _workspace_root() -> Path:
    ws = os.environ.get("ECO_WORKSPACE_DIR", "").strip()
    if ws:
        return Path(ws)
    from agent_core.workspace import WS_ROOT

    return WS_ROOT


def _uploads_dir() -> Path:
    d = _workspace_root() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(name: str) -> str:
    """去路径 + 清洗字符，保留中文/字母/数字/.-_"""
    name = Path(name or "file").name
    name = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", name).strip("._") or "file"
    return name[:120]


def _uniquify(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    for i in range(2, 1000):
        cand = dest.with_name(f"{stem}_{i}{suffix}")
        if not cand.exists():
            return cand
    return dest.with_name(f"{stem}_{int(time.time())}{suffix}")


async def _save_upload(file: UploadFile, max_bytes: int, name_hint: str) -> Path:
    name = _safe_name(name_hint)
    dest = _uniquify(_uploads_dir() / f"{int(time.time())}-{name}")
    size = 0
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_bytes:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"文件超过 {max_bytes // (1024 * 1024)}MB 上限")
            out.write(chunk)
    return dest, size


@router.post("/files")
async def upload_file(file: UploadFile = File(...)) -> dict:
    """附件上传：保存到工作区 uploads/，返回模型可读的服务器路径。"""
    dest, size = await _save_upload(file, MAX_BYTES, file.filename or "upload")
    logger.info("upload saved: %s (%d bytes)", dest, size)
    return {"ok": True, "name": dest.name, "path": str(dest), "size_kb": round(size / 1024, 1)}


# ── 语音转写（飞书妙记）───────────────────────────────────────


def _run_cli(args: list[str], timeout: float, cwd: str | None = None, json_fmt: bool = True) -> dict:
    try:
        cmd = ["lark-cli", *args]
        if json_fmt:
            cmd += ["--format", "json"]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ},
            cwd=cwd,
        )
    except FileNotFoundError:
        return {"ok": False, "error": "lark-cli 未安装（语音转写不可用）"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"lark-cli 超时（>{timeout:.0f}s）"}
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:300]
        return {"ok": False, "error": f"lark-cli 退出码 {proc.returncode}: {err}"}
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "lark-cli 输出非 JSON", "raw": (proc.stdout or "")[:300]}
    return {"ok": True, "data": data}


def _find_token(obj, key: str):
    """递归查找第一个非空 token 字段（兼容不同版本输出结构）。"""
    if isinstance(obj, dict):
        v = obj.get(key)
        if v:
            return str(v)
        for val in obj.values():
            r = _find_token(val, key)
            if r:
                return r
    elif isinstance(obj, list):
        for val in obj:
            r = _find_token(val, key)
            if r:
                return r
    return None


def _transcode_to_m4a(src: Path, deadline: float) -> Path:
    """webm/opus 等妙记不支持的格式 → ffmpeg 转 m4a；失败则原样返回。"""
    if src.suffix.lower() in LARK_MINUTES_AUDIO:
        return src
    out = src.with_suffix(".m4a")
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-vn", "-c:a", "aac", "-b:a", "96k", str(out)],
            capture_output=True,
            text=True,
            timeout=max(1.0, deadline - time.time()),
        )
    except FileNotFoundError:
        return src
    except subprocess.TimeoutExpired:
        return src
    if proc.returncode == 0 and out.exists() and out.stat().st_size > 0:
        return out
    out.unlink(missing_ok=True)
    return src


def _user_identity_ready() -> tuple[bool, str]:
    """检查 lark-cli user 身份是否可用（妙记上传只支持 user 身份）。"""
    r = _run_cli(["auth", "status"], 30, json_fmt=False)
    if not r["ok"]:
        return False, f"无法读取 lark 登录状态: {r['error']}"
    try:
        user = r["data"].get("identities", {}).get("user", {})
    except AttributeError:
        return False, "lark 登录状态返回格式异常"
    if user.get("available"):
        return True, ""
    msg = user.get("message") or "user 身份不可用"
    return False, f"飞书用户身份已过期（{msg}）"


def _transcribe_sync(audio_path: str) -> dict:
    t0 = time.time()
    deadline = t0 + VOICE_TIMEOUT

    def remaining(step: str) -> float:
        left = deadline - time.time()
        if left <= 0:
            raise HTTPException(504, f"语音转写超时（{step} 前已耗尽 {VOICE_TIMEOUT}s）")
        return left

    # 0) 预检 user 身份：妙记上传/读取只支持 user，过期时直接给可操作的报错
    user_ok, user_err = _user_identity_ready()
    if not user_ok:
        return {
            "ok": False,
            "error": f"{user_err}。请在普通终端运行 lark-cli auth login 重新登录后重试；录音已保留在工作区 uploads/",
            "audio_path": audio_path,
        }

    src = Path(audio_path)
    media = _transcode_to_m4a(src, deadline)

    # 1) 上传音频到飞书云盘（lark-cli 要求 --file 是 cwd 内的相对路径）
    r1 = _run_cli(["drive", "+upload", "--file", media.name], remaining("云盘上传"), cwd=str(media.parent))
    if not r1["ok"]:
        return {"ok": False, "error": f"云盘上传失败: {r1['error']}", "audio_path": audio_path}
    file_token = _find_token(r1["data"], "file_token")
    if not file_token:
        return {"ok": False, "error": "云盘上传成功但未返回 file_token（lark 授权可能过期）", "audio_path": audio_path}

    # 2) 生成妙记（妙记只支持 user 身份）
    r2 = _run_cli(["minutes", "+upload", "--file-token", file_token, "--as", "user"], remaining("妙记生成"))
    if not r2["ok"]:
        return {"ok": False, "error": f"妙记生成失败: {r2['error']}", "audio_path": audio_path}
    minute_token = _find_token(r2["data"], "minute_token")
    if not minute_token:
        return {"ok": False, "error": "妙记生成成功但未返回 minute_token", "audio_path": audio_path}

    # 3) 等待转写完成，取逐字稿
    out_dir = _uploads_dir() / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    r3 = _run_cli(
        [
            "minutes",
            "+detail",
            "--minute-tokens",
            minute_token,
            "--wait-ready",
            "--transcript",
            "--output-dir",
            str(out_dir),
            "--as",
            "user",
        ],
        remaining("逐字稿获取"),
    )
    if not r3["ok"]:
        return {"ok": False, "error": f"逐字稿获取失败: {r3['error']}", "audio_path": audio_path}

    transcript_file = _find_token(r3["data"], "transcript_file")
    text = ""
    if transcript_file:
        p = Path(transcript_file)
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                text = ""
    if not text:
        return {
            "ok": False,
            "error": "妙记已生成但逐字稿为空（录音可能无人声，或转写仍在进行，稍后可在飞书妙记中查看）",
            "audio_path": audio_path,
            "minute_token": minute_token,
        }
    return {
        "ok": True,
        "text": text,
        "audio_path": audio_path,
        "minute_token": minute_token,
        "elapsed_s": round(time.time() - t0, 1),
    }


@router.post("/voice/transcribe")
async def voice_transcribe(file: UploadFile = File(...)) -> dict:
    """语音转写：保存录音 → ffmpeg 转码 → 飞书妙记逐字稿。"""
    name = _safe_name(file.filename or "voice.webm")
    if not name.lower().endswith(
        (".webm", ".mp3", ".m4a", ".wav", ".ogg", ".mp4", ".aac", ".flac", ".opus", ".amr", ".wma", ".mov")
    ):
        name += ".webm"
    dest, size = await _save_upload(file, AUDIO_MAX_BYTES, name)
    if size < MIN_AUDIO_BYTES:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "录音太短（<2KB），未收到有效语音，请重新录制")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _transcribe_sync, str(dest))
    result["audio_path"] = str(dest)
    return result
