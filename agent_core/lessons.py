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
_FAILURE_HINTS = (
    "找不到",
    "未收录",
    "404",
    "未找到",
    "不在",
    "失败",
    "被拒",
    "没有找到",
    "未检索到",
    "无结果",
    "不存在",
    "超时",
    "timed out",
    "timeout",
)

# 否定式排除：这些句式里出现失败词，恰恰说明「没失败」。
# 真实污染案例：某轮回复写着「…返回了有效结果：当前娄底市AQI 50…
# 没有其他查询任务失败」，因含「失败」二字被判为失败并沉淀成教训，
# 关键词落成 ['你好']。此后每次寒暄都注入「曾用 query_air_quality
# 处理此问题」，模型照做 → 再次误调 → 再沉淀，形成自我强化的错误循环。
_NEGATED_FAILURE = (
    "没有其他", "没有任何", "均未失败", "没有失败", "未失败",
    "不存在失败", "没有出现失败", "无失败",
)

# 明确成功的信号：出现即不沉淀 —— 成功不是教训。
_SUCCESS_HINTS = (
    "返回了有效结果", "查询成功", "已获取到", "获取成功",
    "已成功", "调用成功", "取到了", "结果如下",
)

# 寒暄/元对话：没有稳定领域语义，作为教训主题会污染此后所有同类问题。
_GREETING_PATTERNS = (
    "你好", "您好", "在吗", "在不在", "你是谁", "你叫什么",
    "你能做什么", "你可以做什么", "可以帮我做哪些", "能帮我做哪些",
    "谢谢", "多谢", "再见", "hello",
)

# 召回门槛：泛词单独命中不足以召回（"你好"曾因此拉出空气质量教训）。
# 长度 >= 该值的关键词视为足够特指，可单独命中
#（如"生态环境保护督察工作条例"）。
_SPECIFIC_KEYWORD_MIN_LEN = 6


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
        for line in self._lessons:
            kws = line.get("keywords", [])
            matched = [kw for kw in kws if kw and kw in text]
            hits = len(matched)
            # 单个短泛词命中不足以召回（"你好"曾因此拉出空气质量教训）；
            # 足够长的专有名词本身已特指，允许单独命中。
            if hits >= 2 or any(len(kw) >= _SPECIFIC_KEYWORD_MIN_LEN for kw in matched):
                scored.append((hits, line))
        scored.sort(key=lambda x: -x[0])
        return [line for _, line in scored[:limit]]

    def stats(self) -> dict:
        return {"lessons": len(self._lessons), "size_bytes": self.path.stat().st_size if self.path.exists() else 0}


def extract_lesson(user_msg: str, reply: str, tool_names: list[str]) -> dict | None:
    """从一轮失败对话中提炼教训（规则版：无需再调 LLM，零成本）。

    只沉淀"有据可查"的确定性教训：工具尝试过 + 回复含失败特征。
    """
    if not tool_names:
        return None
    reply = str(reply)

    # 寒暄/元对话不作教训主题：没有稳定领域语义，沉淀后会污染此后所有同类问题。
    # 只在寒暄构成消息主体时拦截 —— 「你好，帮我查一下危险废物贮存标准」
    # 是寒暄前缀 + 真实业务诉求，那条业务教训仍应沉淀（关键词侧会剔掉寒暄词）。
    _msg = str(user_msg).strip().lower()
    _residual = _msg
    for g in _GREETING_PATTERNS:
        _residual = _residual.replace(g, "")
    _residual = _residual.strip(" ，,。.!！?？、~…")
    if any(g in _msg for g in _GREETING_PATTERNS) and len(_residual) < 6:
        return None

    # 明确成功不是教训
    if any(h in reply for h in _SUCCESS_HINTS):
        return None

    if not any(hint in reply for hint in _FAILURE_HINTS):
        return None

    # 否定式排除：「没有其他查询任务失败」这类句子里的失败词不算失败
    if any(neg in reply for neg in _NEGATED_FAILURE):
        return None
    # 严格判失败：失败特征须出现在回复开头（真实错误报告），或回复极短。
    # 长回复中部出现"未检索到/0命中"是正常的诚实标注（[待确认]），不是失败。
    head = reply[:400]
    if not any(hint in head for hint in _FAILURE_HINTS) and len(reply) > 500:
        return None

    # 教训主题 = 用户消息里的关键名词（去停用词）
    stopwords = {"的", "了", "吗", "呢", "在", "是", "有", "和", "与", "请", "帮", "我", "你"}
    kws = [w for w in re.findall(r"[\u4e00-\u9fff]{2,8}", str(user_msg))
           if w not in stopwords
           and not any(g in w for g in _GREETING_PATTERNS)][:8]

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
