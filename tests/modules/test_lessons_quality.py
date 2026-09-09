#!/usr/bin/env python3
"""tests/modules/test_lessons_quality.py — 教训沉淀的准入与召回质量

背景（一条自我强化的错误循环，已在运行时完整定位）：

  1. 历史上有人问过「你好」，那一轮误调了 query_air_quality；
  2. extract_lesson 把这次**成功的调用**误判成"教训"落了库，
     关键词记成 ['你好']，教训正文写着
     「曾尝试用 query_air_quality 处理此问题，结果：…返回了有效结果：
       当前娄底市AQI 50…没有其他查询任务失败」；
  3. 此后每次有人说「你好」，这条教训就被注入系统提示词，
     明示"曾用 query_air_quality 处理此问题"；
  4. 模型照做 → 再次误调 → 又可能再沉淀。

  误判的直接原因：回复里「没有其他查询任务失败」含「失败」二字，
  而 _FAILURE_HINTS 只做子串匹配，否定句被当成失败特征。
  召回侧则是 hits>=1 即命中，单个高频词（"你好"）就能拉出无关教训。

本文件锁死三条：
  · 明确成功的回复不得沉淀为教训（含否定式"没有…失败"）；
  · 寒暄/元对话不得作为教训主题；
  · 召回需要足够的关键词证据，单个泛词不足以命中。
"""

from __future__ import annotations

from agent_core.lessons import LessonStore, extract_lesson


# ── 准入：成功不是教训 ───────────────────────────────────────────
def test_negated_failure_word_is_not_a_failure():
    """「没有其他查询任务失败」不得被当成失败特征。

    这正是污染库的那条真实回复的句式。
    """
    got = extract_lesson(
        "你好",
        "上一轮仅查询娄底市空气质量，返回了有效结果：当前娄底市AQI 50，"
        "空气质量级别优。没有其他查询任务失败，请问您需要查询什么具体内容？",
        ["query_air_quality"])
    assert got is None, "把成功调用沉淀成了教训"


def test_explicit_success_is_not_a_lesson():
    """回复明示取到有效结果时，不得沉淀。"""
    for reply in (
        "返回了有效结果：当前AQI 50。",
        "查询成功，PM2.5 为 35 μg/m³。",
        "已获取到数据，冷水江今日空气质量为优。",
    ):
        assert extract_lesson("查空气质量", reply, ["query_air_quality"]) is None, reply


def test_real_failure_is_still_captured():
    """真失败必须照常沉淀 —— 加严准入不能把有用教训一起挡掉。"""
    got = extract_lesson(
        "查一下某企业排污许可证",
        "查询失败：远程服务当前不可用（重连失败）。未获取到任何记录。",
        ["permit_pub_search"])
    assert got is not None
    assert "permit_pub_search" in got["lesson"]


# ── 准入：寒暄不该成为教训主题 ───────────────────────────────────
def test_greeting_never_becomes_a_lesson_topic():
    """寒暄/元对话即便那轮真失败了，也不该沉淀成主题教训。

    「你好」这种问题没有稳定的领域语义，沉淀后会污染此后所有寒暄。
    """
    for msg in ("你好", "在吗", "你是谁", "你能做什么", "谢谢", "你现在可以帮我做哪些工作"):
        got = extract_lesson(msg, "查询失败：服务不可用。", ["query_air_quality"])
        assert got is None, f"寒暄被沉淀为教训: {msg}"


def test_lesson_keywords_exclude_greeting_tokens():
    """即便主题合法，关键词里也不得混入寒暄词。"""
    got = extract_lesson(
        "你好，帮我查一下危险废物贮存标准",
        "查询失败：未检索到相关标准。",
        ["statute_search"])
    assert got is not None
    assert "你好" not in got["keywords"]


# ── 召回：单个泛词不足以命中 ─────────────────────────────────────
def test_single_generic_keyword_does_not_recall(tmp_path):
    """一个泛词命中一条教训是不够的 —— 否则"你好"会拉出空气质量教训。"""
    store = LessonStore(path=tmp_path / "lessons.jsonl")
    store.add({"keywords": ["你好"], "lesson": "曾用 query_air_quality 处理此问题",
               "source": "test", "when": 0})
    assert store.search("你好") == [], "单个泛词仍能召回无关教训"


def test_multi_keyword_match_still_recalls(tmp_path):
    """两个及以上关键词命中时照常召回，保留能力。"""
    store = LessonStore(path=tmp_path / "lessons.jsonl")
    store.add({"keywords": ["危险废物", "贮存", "标准"],
               "lesson": "statute_search 未收录该标准，改用 analyze_document",
               "source": "test", "when": 0})
    got = store.search("危险废物贮存有什么标准要求")
    assert len(got) == 1


def test_domain_specific_single_keyword_still_recalls(tmp_path):
    """长专有名词单独命中仍应召回 —— 它本身已足够特指。"""
    store = LessonStore(path=tmp_path / "lessons.jsonl")
    store.add({"keywords": ["生态环境保护督察工作条例"],
               "lesson": "该党内法规不在 statute_lookup 库内",
               "source": "test", "when": 0})
    got = store.search("生态环境保护督察工作条例第几条规定的")
    assert len(got) == 1, "足够特指的长词应当能单独召回"
