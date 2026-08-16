#!/usr/bin/env python3
"""
agent_core/lessons.py — 对话教训自动沉淀（自愈闭环的对话侧）

设计:
  - 对话结束后自动提炼"这轮遇到的坑 + 解法"为一条 lesson，
    写入 lessons.jsonl（不需要人工改提示词）
  - 下次构建系统提示词时，按当前消息关键词检索相关 lesson 注入
    【历史经验】层——模型自动避开已知坑
  - 触发条件: 回复含失败特征（找不到/404/未收录/失败/被拒）或
    工具调用出错，且确有工具尝试过

闭环:
  对话踩坑 → (自动) 提炼教训 → 存 lesson
      ↓
  下次对话 → 检索相关经验 → 注入提示词 → 不再踩坑
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path

logger = logging.getLogger("eco.lessons")

DATA_DIR = Path(__file__).resolve().parent.parent / "memory-tree" / "data"
LESSONS_FILE = DATA_DIR / "lessons.jsonl"

# 失败特征（触发提炼的信号）
_FAILURE_HINTS = ("找不到", "未收录", "404", "未找到", "不在", "失败", "被拒",
                  "没有找到", "未检索到", "无结果", "不存在",
                  "超时", "timed out", "timeout")


class LessonStore:
    """教训库：append + 关键词检索。"""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else LESSONS_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._lessons: list[dict] = self._load()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def add(self, lesson: dict) -> dict:
        """追加一条教训: {keywords, lesson, source, when}。"""
        with self._lock:
            self._lessons.append(lesson)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(lesson, ensure_ascii=False) + "\n")
        return lesson

    def search(self, text: str, limit: int = 2) -> list[dict]:
        """按关键词交集检索相关教训（简单可靠，无向量依赖）。"""
        text = str(text)
        scored = []
        for l in self._lessons:
            kws = l.get("keywords", [])
            hits = sum(1 for kw in kws if kw and kw in text)
            if hits:
                scored.append((hits, l))
        scored.sort(key=lambda x: -x[0])
        return [l for _, l in scored[:limit]]

    def stats(self) -> dict:
        return {"lessons": len(self._lessons),
                "size_bytes": self.path.stat().st_size if self.path.exists() else 0}


def extract_lesson(user_msg: str, reply: str, tool_names: list[str]) -> dict | None:
    """从一轮失败对话中提炼教训（规则版：无需再调 LLM，零成本）。

    只沉淀"有据可查"的确定性教训：工具尝试过 + 回复含失败特征。
    """
    if not tool_names:
        return None
    reply = str(reply)
    if not any(hint in reply for hint in _FAILURE_HINTS):
        return None
    # 严格判失败：失败特征须出现在回复开头（真实错误报告），或回复极短。
    # 长回复中部出现"未检索到/0命中"是正常的诚实标注（[待确认]），不是失败。
    head = reply[:400]
    if not any(hint in head for hint in _FAILURE_HINTS) and len(reply) > 500:
        return None

    # 教训主题 = 用户消息里的关键名词（去停用词）
    stopwords = {"的", "了", "吗", "呢", "在", "是", "有", "和", "与", "请", "帮", "我", "你"}
    kws = [w for w in re.findall(r"[\u4e00-\u9fff]{2,8}", str(user_msg))
           if w not in stopwords][:8]

    # 失败原因（从回复提取第一句含失败特征的话）
    reason_m = re.search(rf"[^。]*(?:{'|'.join(_FAILURE_HINTS)})[^。]*。", reply)
    reason = reason_m.group(0)[:120] if reason_m else reply[:120]

    return {
        "keywords": kws,
        "lesson": f"曾尝试用 {', '.join(tool_names[:4])} 处理此问题，结果：{reason}。"
                  f"下次先原样重试一次（多为瞬时网络故障），仍失败再换关键词/渠道。",
        "source": "auto-extract",
        "when": time.time(),
    }


def get_lesson_store() -> LessonStore:
    global _store
    if _store is None:
        _store = LessonStore()
    return _store


_store: LessonStore | None = None
