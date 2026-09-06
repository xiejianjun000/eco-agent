#!/usr/bin/env python3
"""
task_log.py — 任务段记忆（WorkBuddy .workbuddy/memory 对标）

按天一份工作日志：`memory-tree/data/task-log/YYYY-MM-DD.md`
任务完成即追加一段 `## 任务标题` + 要点（做了什么/关键结果/工具/产物），
下次会话把近 N 天日志注入 prompt（跨会话任务记忆）。

格式与 WorkBuddy `.workbuddy/memory/YYYY-MM-DD.md` 对齐：
    # 2026-09-01 工作日志

    ## 任务标题（13:25）
    - 做了什么：……
    - 结果：……
    - 工具：read, write
    - 产物：artifacts/xxx.md
"""

from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger("task_log")

ROOT = Path(__file__).resolve().parent.parent
TASK_LOG_DIR = ROOT / "memory-tree" / "data" / "task-log"
_lock = threading.Lock()


def _task_title(message: str) -> str:
    """任务标题：消息首行清洗后截断 40 字。"""
    first = next((ln.strip() for ln in (message or "").splitlines() if ln.strip()), "")
    return re.sub(r"[^\w\u4e00-\u9fff]+", " ", first)[:40].strip() or "任务"


def append_task_log(message: str, reply: str, trace: list | None = None) -> str | None:
    """任务完成后追加一段到当日工作日志；返回文件路径，失败返回 None。

    幂等去重：同一天已存在同标题段落则跳过（避免流式/非流式双写）。
    """
    try:
        title = _task_title(message)
        trace = trace or []
        now = datetime.now()
        fname = now.strftime("%Y-%m-%d")
        path = TASK_LOG_DIR / f"{fname}.md"

        # 段内容
        lines: list[str] = [f"## {title}（{now.strftime('%H:%M')}）"]
        lines.append(f"- 做了什么：{(message or '').strip()[:120] or title}")
        first_reply = next((ln.strip() for ln in (reply or "").splitlines() if ln.strip()), "")
        if first_reply:
            lines.append(f"- 结果：{first_reply[:120]}")
        tool_names = [t.get("name", "") for t in trace if t.get("type") == "tool"]
        if tool_names:
            lines.append(f"- 工具：{', '.join(tool_names[:8])}")
        artifacts = [t.get("path", "") for t in trace if t.get("type") == "artifact" and t.get("path")]
        docs = [t.get("url", "") for t in trace if t.get("type") == "document" and t.get("url")]
        for p in artifacts[:3]:
            lines.append(f"- 产物：{p}")
        for u in docs[:2]:
            lines.append(f"- 文档：{u}")
        block = "\n".join(lines)

        with _lock:
            TASK_LOG_DIR.mkdir(parents=True, exist_ok=True)
            header = f"# {fname} 工作日志\n\n"
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="replace")
                # 去重：同标题段落已存在
                if f"## {title}（" in text:
                    return str(path)
                # 避免段之间无空行
                text = text.rstrip() + "\n\n" + block + "\n"
            else:
                text = header + block + "\n"
            path.write_text(text, encoding="utf-8")
        logger.info("[task_log] %s 已追加: %s", fname, title)
        return str(path)
    except Exception as e:  # noqa: BLE001 — 日志失败不影响对话
        logger.warning("task_log append failed: %s", e)
        return None


def load_recent_task_logs(days: int = 7, max_chars: int = 3000) -> str:
    """近 N 天任务日志拼接（供 prompt 注入），按天倒序，截断防爆上下文。"""
    out: list[str] = []
    try:
        if not TASK_LOG_DIR.is_dir():
            return ""
        today = datetime.now().date()
        for i in range(days):
            d = today - timedelta(days=i)
            p = TASK_LOG_DIR / f"{d.strftime('%Y-%m-%d')}.md"
            if p.is_file():
                out.append(p.read_text(encoding="utf-8", errors="replace").strip())
        joined = "\n\n".join(out)
        return joined[:max_chars]
    except Exception as e:  # noqa: BLE001
        logger.warning("task_log load failed: %s", e)
        return ""


def stats() -> dict:
    try:
        files = sorted(TASK_LOG_DIR.glob("*.md")) if TASK_LOG_DIR.is_dir() else []
        return {"days": len(files), "files": [f.name for f in files[-7:]]}
    except Exception:  # noqa: BLE001
        return {"days": 0, "files": []}


# ===== 自测 =====

def test():
    import tempfile
    global TASK_LOG_DIR
    tmp = Path(tempfile.mkdtemp(prefix="tasklog-test-"))
    TASK_LOG_DIR = tmp
    trace = [{"type": "tool", "name": "statute_lookup"},
             {"type": "artifact", "path": "/tmp/art/xxx.md", "title": "执法建议"}]
    p1 = append_task_log("查询大气法并生成执法建议", "已生成执法建议文书，见产物", trace)
    p2 = append_task_log("查询大气法并生成执法建议", "重复调用", trace)  # 应去重
    p3 = append_task_log("另一个任务", "完成", [])
    print("p1:", p1)
    print("去重(p2=None?):", p2, "(p2 应等于 p1 路径，内容不重复)")
    print("--- 文件内容 ---")
    print(Path(p3).read_text(encoding="utf-8"))
    logs = load_recent_task_logs(days=7)
    assert "执法建议" in logs and "另一个任务" in logs
    print("--- 近7天注入内容含 2 个任务段:", "执法建议" in logs and "另一个任务" in logs, "---")
    print("\n[OK] task_log 自测通过")


if __name__ == "__main__":
    test()
