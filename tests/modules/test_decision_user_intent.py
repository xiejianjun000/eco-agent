#!/usr/bin/env python3
"""tests/modules/test_decision_user_intent.py — 决策留痕必须能定位到提问

为什么加这个字段（真实验收事故）：

  军哥定的验收协议是「他发提示词、我在后台看决策链和轨迹、他把输出发我核」。
  实际执行时我从留痕里只看到：

      #1 r1 stop        实选=[]
      #2 r1 tool_calls  实选=['hunan_realtime']

  **无法确定哪条记录对应哪个提问**，只能靠时间先后猜。
  当他连发六条探针、其中两条是直接复制的旧回答时，
  这种猜法就会张冠李戴 —— 而这恰恰是最需要分辨清楚的场合。

  宪法 G8「可追溯性」要求「每条结论可回溯到原始依据」。
  留痕若不能定位到问题本身，就不满足这条。

隐私边界（本文件重点锁死的部分）：

  审计链是 SM3 append-only —— 不可篡改，也**不可删除**。
  用户问题里可能带企业名、人名、地址、案卷号、许可证号。
  全文入链等于永久留存这些内容，一旦写进去就没有补救手段。
  所以只存 40 字摘要：足够定位是哪一问，又不足以构成完整的敏感信息载体。
  这个上限是安全设计，不是省空间 —— 不得以「方便排查」为由放宽。
"""

from __future__ import annotations

import json

from agent_core.decisions import record_decision
from server.api.chat import _pick_user_intent


def _last_payload(path) -> dict:
    line = path.read_text(encoding="utf-8").strip().splitlines()[-1]
    return json.loads(json.loads(line)["content"])


def test_user_intent_is_recorded(tmp_path):
    """提问摘要必须落到留痕里，否则无法按提问反查。"""
    p = tmp_path / "d.jsonl"
    record_decision(
        candidate_tools=10, selected_tools=[], finish_reason="stop",
        user_intent="娄底今天空气质量怎么样", path=p)
    assert _last_payload(p)["user_intent"] == "娄底今天空气质量怎么样"


def test_two_records_are_distinguishable(tmp_path):
    """两条形态完全相同的留痕，必须能靠 user_intent 区分开。

    这正是验收时踩到的坑：两条都是 r1/stop/零工具，肉眼无从分辨。
    """
    p = tmp_path / "d.jsonl"
    record_decision(candidate_tools=10, selected_tools=[], finish_reason="stop",
                    user_intent="你好", path=p)
    record_decision(candidate_tools=10, selected_tools=[], finish_reason="stop",
                    user_intent="火星今天的空气质量是多少", path=p)
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    intents = [json.loads(json.loads(x)["content"])["user_intent"] for x in lines]
    assert intents == ["你好", "火星今天的空气质量是多少"]
    assert len(set(intents)) == 2, "两条留痕无法区分"


def test_long_question_is_truncated_to_40_chars(tmp_path):
    """超长提问必须截断 —— 审计链不可删除，全文入链无法补救。"""
    p = tmp_path / "d.jsonl"
    long_q = "冷水江市锑冶炼企业" * 20  # 180 字
    record_decision(candidate_tools=1, selected_tools=[], finish_reason="stop",
                    user_intent=long_q, path=p)
    got = _last_payload(p)["user_intent"]
    assert len(got) == 40, f"截断长度不对：{len(got)}"
    assert got == long_q[:40]


def test_newlines_are_flattened(tmp_path):
    """换行必须压平，否则破坏单行 JSONL 结构。"""
    p = tmp_path / "d.jsonl"
    record_decision(candidate_tools=1, selected_tools=[], finish_reason="stop",
                    user_intent="第一行\n第二行\r\n第三行", path=p)
    got = _last_payload(p)["user_intent"]
    assert "\n" not in got and "\r" not in got
    assert got == "第一行 第二行 第三行"
    # 文件必须仍是合法 JSONL（每行独立可解析）
    for line in p.read_text(encoding="utf-8").strip().splitlines():
        json.loads(line)


def test_missing_intent_defaults_to_empty(tmp_path):
    """不传 user_intent 不得报错 —— 留痕是旁路，绝不能影响主流程。"""
    p = tmp_path / "d.jsonl"
    record_decision(candidate_tools=1, selected_tools=[],
                    finish_reason="stop", path=p)
    assert _last_payload(p)["user_intent"] == ""


def test_chain_integrity_still_holds(tmp_path):
    """加字段不得破坏 SM3 链的 prev_hash 衔接。"""
    p = tmp_path / "d.jsonl"
    for q in ("你好", "查许可证", "算超标倍数"):
        record_decision(candidate_tools=1, selected_tools=[],
                        finish_reason="stop", user_intent=q, path=p)
    recs = [json.loads(x) for x in p.read_text(encoding="utf-8").strip().splitlines()]
    for prev, cur in zip(recs, recs[1:]):
        assert cur["prev_hash"] == prev["hash"], "SM3 链断裂"


# ── 提取逻辑：必须跳过系统以 role="user" 注入的伪提问 ──────────────────
#
# 两次翻车都在这里，值得把反例锁死：
#   v1 取「最后一条 role=user」→ 抓到反思回路的「注意：上一轮部分工具…」
#   v2 改取「首条 role=user」  → 首轮对，但有历史时抓到上一轮旧提问；
#                                 实测 r4/r5 仍抓到注入
# 根因：chat.py 有 6 处 messages.append({"role": "user"}) 是系统注入，
# 与真实提问结构完全同形，只能按已知措辞排除。

def test_skips_reflection_injection():
    """反思回路注入排在真实提问之后，不得被当成提问。"""
    msgs = [
        {"role": "system", "content": "你是 eco Agent"},
        {"role": "user", "content": "娄底今天空气质量怎么样"},
        {"role": "assistant", "content": ""},
        {"role": "tool", "content": "{}"},
        {"role": "user", "content": "注意：上一轮部分工具返回了失败或空结果。请先判断原因"},
    ]
    assert _pick_user_intent(msgs) == "娄底今天空气质量怎么样"


def test_skips_all_six_injection_kinds():
    """6 种系统注入全部要跳过——逐一锁死，新增注入时这里会失败提醒。"""
    injections = [
        "注意：上一轮部分工具返回了失败或空结果。请先判断原因",
        "已达本轮时间预算，工具检索到此为止。请基于上面工具返回的真实结果",
        "工具检索已结束。请基于上面工具返回的真实结果直接给出最终回答。",
        "你上一条回答存在质量问题：坐标与工具返回不一致。请修正",
        "禁止输出 tool_calls、invoke 等任何工具调用格式（含全角符号），",
        "你尚未调用 save_document。请立即调用 save_document ",
    ]
    for inj in injections:
        msgs = [
            {"role": "user", "content": "真实提问"},
            {"role": "user", "content": inj},
        ]
        assert _pick_user_intent(msgs) == "真实提问", f"未跳过：{inj[:20]}"


def test_takes_latest_real_question_not_first():
    """有历史时取最后一条真实提问——首条是上一轮的旧问题。"""
    msgs = [
        {"role": "user", "content": "上一轮的旧提问"},
        {"role": "assistant", "content": "旧回答"},
        {"role": "user", "content": "本轮的新提问"},
    ]
    assert _pick_user_intent(msgs) == "本轮的新提问"


def test_real_question_resembling_injection_is_kept():
    """用户真问「工具检索是怎么结束的」不能被误杀——只排除完整前缀。"""
    msgs = [{"role": "user", "content": "工具检索是怎么结束的？给我讲讲机制"}]
    assert _pick_user_intent(msgs) == "工具检索是怎么结束的？给我讲讲机制"


def test_all_injections_returns_empty_not_crash():
    """全是注入时返回空串，绝不抛异常——留痕是旁路。"""
    msgs = [{"role": "user", "content": "工具检索已结束。请基于上面"}]
    assert _pick_user_intent(msgs) == ""


def test_empty_and_malformed_input():
    """空/None/脏数据不得抛异常。"""
    assert _pick_user_intent([]) == ""
    assert _pick_user_intent(None) == ""
    assert _pick_user_intent([None, "str", 42, {"role": "user"}]) == ""
