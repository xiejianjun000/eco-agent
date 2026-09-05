#!/usr/bin/env python3
"""
agent_core/workflow.py — Workflow 编排（对标 DSH packages/workflow）

脚本在独立子进程执行（隔离：崩溃/超时不拖垮 server），子进程内提供
编排 hooks，脚本体为同步 Python（top-level 风格，无需 async）：

  agent(prompt, label=None, model='') -> str   前台子代理执行，返回结果文本
  pipeline(items, *stages) -> list            每个 item 依次过各阶段（无跨阶段 barrier）
  parallel(thunks) -> list                    并发执行零参函数，单点失败得 None
  phase(title) / log(message)                 进度与日志（收集到返回的 log 列表）
  args                                         调用方传入的 JSON 参数（global）

脚本最后一条表达式的值若可 JSON 序列化则作为结果返回；
返回 (result, log, duration_ms)。

安全边界（如实声明）：脚本在本机子进程执行、可 import 本机模块，
按受信任代码对待（与 execute_code L3 同级）；agent() 内部走正常工具
权限闸门。超时强制 kill。
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("eco.workflow")

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TIMEOUT = 600

# 子进程 wrapper：提供 hooks + exec 脚本 + JSON 结果回传
_WRAPPER = r'''
import asyncio
import concurrent.futures
import json
import sys
import time

_log = []
_result = None
_args = json.loads(sys.stdin.read() or "{}")

def phase(title):
    _log.append({"type": "phase", "title": str(title)})
    print(f"[phase] {title}", file=sys.stderr)

def log(message):
    _log.append({"type": "log", "message": str(message)})
    print(f"[log] {message}", file=sys.stderr)

def agent(prompt, label=None, model=""):
    """前台子代理：执行一次完整工具循环，返回结果文本。"""
    from agent_core.subagent import Subagent
    from agent_core.llm_client import get_default_client

    sub = Subagent(str(prompt), label=label or "", model=model or "")
    client = get_default_client()
    from server.api.chat import _build_messages, _chat_with_codex_loop
    messages = _build_messages(str(prompt), [])

    async def _run():
        return await _chat_with_codex_loop(client, messages, model)

    reply, _trace, _usage, _ft, _ftok = asyncio.run(_run())
    _log.append({"type": "agent", "label": label or "", "chars": len(reply or "")})
    return reply or ""

def pipeline(items, *stages):
    """每 item 依次过各阶段（独立推进，无跨阶段 barrier）。"""
    out = []
    for idx, item in enumerate(items):
        current = item
        try:
            for stage in stages:
                current = stage(current, item, idx)
        except Exception as e:
            _log.append({"type": "error", "item": idx, "error": f"{type(e).__name__}: {e}"})
            current = None
        out.append(current)
    return out

def parallel(thunks):
    """并发执行零参函数（barrier：全部完成后返回）。"""
    def _run_one(t):
        try:
            return t()
        except Exception as e:
            _log.append({"type": "error", "error": f"{type(e).__name__}: {e}"})
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(_run_one, thunks))

try:
    code = sys.argv[1]
    ns = {"agent": agent, "pipeline": pipeline, "parallel": parallel,
          "phase": phase, "log": log, "args": _args}
    exec(compile(code, "<workflow>", "exec"), ns)
    for name in ("result", "RESULT"):
        if name in ns:
            _result = ns[name]
            break
except SystemExit:
    pass
except Exception as e:
    _log.append({"type": "fatal", "error": f"{type(e).__name__}: {e}"})
    _result = {"error": f"{type(e).__name__}: {e}"}

print(json.dumps({"result": _result, "log": _log}, ensure_ascii=False, default=str))
'''


def run_workflow(script: str, args: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """执行编排脚本。返回 {ok, result, log, duration_ms}。"""
    args = args or {}
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _WRAPPER, script],
            input=json.dumps(args, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        duration_ms = int((time.time() - t0) * 1000)
        out = proc.stdout.strip()
        if not out:
            return {
                "ok": False,
                "error": f"无输出（exit={proc.returncode}）",
                "stderr": proc.stderr[-800:],
                "duration_ms": duration_ms,
            }
        payload = json.loads(out)
        return {
            "ok": proc.returncode == 0,
            "result": payload.get("result"),
            "log": payload.get("log", []),
            "duration_ms": duration_ms,
            "stderr_tail": proc.stderr[-500:] if proc.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"超时（>{timeout}s），已强制终止", "duration_ms": int((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "duration_ms": int((time.time() - t0) * 1000)}
