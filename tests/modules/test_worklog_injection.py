#!/usr/bin/env python3
"""tests/modules/test_worklog_injection.py — 工作日志注入的相关性门槛

背景（运行时完整定位的真实缺陷，也是「你好」误调工具的真凶）：

  server/api/chat.py 的 _build_messages 会把近 7 天工作日志（2500 字符）
  **无条件**注入每一次对话的系统提示词。而日志内容长这样：

      # 2026-09-09 工作日志
      ## 我觉得你在吹牛（00:55）
      - 结果：✅ 已经拿到娄底市实时空气质量数据，结果如下：
      - 工具：query_air_quality
      ## 你会玩地图吗（00:59）
      - 工具：inspect, api_probe, execute_code, chart_render

  也就是说，日志里全是「闲聊输入 → 却调了空气质量/地图工具」的**成功范例**，
  模型把它当示范照做。于是问「你好」会去查娄底空气质量、画点位图、
  甚至连查八轮（实测最长 117 秒、8 个工具）。

  排查过程中先后试过降低工具温度（0.7→0.1）与清理教训库（清掉 12 条毒教训），
  两者都没解决 —— 因为真正的示范来自这段日志注入。这也是一次教训：
  改之前必须先看模型真正收到了什么，而不是从合理猜测开始改。

本文件锁死：日志注入必须与当前问题相关；寒暄类输入不得携带工具调用范例。
"""

from __future__ import annotations

from server.api.chat import _worklog_is_relevant


# ── 寒暄/元对话不注入日志 ────────────────────────────────────────
def test_greeting_gets_no_worklog():
    """寒暄不该带入任何历史工具调用范例。"""
    for msg in ("你好", "您好", "在吗", "你是谁", "谢谢", "你能做什么",
                "hello", "hi"):
        assert _worklog_is_relevant(msg) is False, f"寒暄仍注入日志: {msg}"


def test_trivial_arithmetic_gets_no_worklog():
    """纯算术/常识不需要历史任务上下文。"""
    for msg in ("1+1等于几", "3的平方", "一吨等于多少公斤"):
        assert _worklog_is_relevant(msg) is False, msg


def test_short_input_gets_no_worklog():
    """极短输入信息量不足，注入 2500 字符日志得不偿失。"""
    assert _worklog_is_relevant("嗯") is False
    assert _worklog_is_relevant("好的") is False


# ── 真实业务问题照常注入 ─────────────────────────────────────────
def test_business_question_keeps_worklog():
    """涉及具体任务/延续性工作的提问必须保留日志注入。"""
    for msg in (
        "继续昨天的排污许可证核查",
        "上次那个案卷评查做到哪一步了",
        "把娄底市空气质量数据整理成报告",
        "危险废物贮存标准有哪些要求",
        "帮我查一下冷水江市的执法案例",
    ):
        assert _worklog_is_relevant(msg) is True, f"业务问题丢了日志注入: {msg}"


def test_continuation_words_keep_worklog():
    """「继续/接着/刚才/上次」这类延续语义最需要日志。"""
    for msg in ("继续", "接着做", "刚才那个报告呢", "上次的结果在哪"):
        assert _worklog_is_relevant(msg) is True, msg


# ── 边界：寒暄前缀 + 业务诉求，按业务处理 ─────────────────────────
def test_greeting_prefix_with_real_request_keeps_worklog():
    """「你好，帮我查危险废物贮存标准」应按业务问题处理。"""
    assert _worklog_is_relevant("你好，帮我查一下危险废物贮存标准") is True


def test_empty_input_is_safe():
    """空输入不得抛错。"""
    assert _worklog_is_relevant("") is False
    assert _worklog_is_relevant(None) is False
