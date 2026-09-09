#!/usr/bin/env python3
"""tests/modules/test_worklog_stale_filter.py — 过期结论不得注入提示词

真实事故（人工验收时抓到的）：

  军哥按协议连发探针，第 2、3 条回答末尾都冒出一句
  「上一轮返回本身成功，非查询失败」——
  一句模型不该说的元叙述。溯源到注入的工作日志第一条：

      ## 查询娄底市的排污许可证信息 前3条（00:03）
      - 结果：确认排污许可公开端MCP未连通：根据api_probe探测结果，
              `eco-pollution-permit-remote` MCP服务器当前未连通
              （`connected: false`），无法调用…

  这条结论写下时是真的，但连接器修好后就过期了。它仍被每轮注入，
  模型据此认为该域查不了，并模仿这种「解释上一轮到底算不算失败」的口吻。
  同一份日志里还有两条「LLM 调用失败: HTTP 402」——纯基础设施故障，
  与业务无关，却一样占着模型的注意力。

  这是 ① 的残留缺口：上一轮我加了「该不该注入」的相关性门槛
  （_worklog_is_relevant），但没管**注入的内容本身是否还成立**。

设计边界：只滤会随时间失效的两类（连通性结论、基础设施故障）。
「参数填错了」「这个标准要查附录」这类不随时间失效的真实教训必须保留 ——
否则就是用一个缺陷换另一个缺陷。
"""

from __future__ import annotations

from agent_core.task_log import _drop_stale_entries


def test_drops_connectivity_conclusion():
    """连通性结论会过期，必须丢弃。"""
    md = """# 2026-09-09 工作日志

## 查询排污许可证（00:03）
- 结果：确认排污许可公开端MCP未连通（`connected: false`），无法调用。

## 查询空气质量（00:10）
- 结果：✅ 娄底市 AQI 47。
"""
    out = _drop_stale_entries(md)
    assert "未连通" not in out
    assert "connected: false" not in out
    assert "查询空气质量" in out, "误伤了正常条目"
    assert "AQI 47" in out


def test_drops_infrastructure_failure():
    """HTTP 402 这类基础设施故障与业务无关，必须丢弃。"""
    md = """# 日志

## 你好（00:05）
- 结果：[eco-server] LLM 调用失败: HTTP 402

## 查标准（00:20）
- 结果：✅ 找到 GB 18597。
"""
    out = _drop_stale_entries(md)
    assert "HTTP 402" not in out
    assert "LLM 调用失败" not in out
    assert "GB 18597" in out


def test_keeps_real_lesson_that_does_not_expire():
    """不随时间失效的真实教训必须保留 —— 这是本过滤器的边界。"""
    md = """# 日志

## 查危废名录（01:00）
- 结果：参数填错了，city 要传行政区划代码而不是中文名。

## 查标准附录（01:10）
- 结果：HW08 的具体代码在名录附录里，正文查不到。
"""
    out = _drop_stale_entries(md)
    assert "参数填错了" in out, "误删了不会过期的真实教训"
    assert "附录" in out


def test_drops_whole_entry_not_just_the_line():
    """按条丢弃，不留残缺条目 —— 半条日志比没有日志更容易误导。"""
    md = """# 日志

## 查许可证（00:03）
- 做了什么：查询娄底市排污许可证。
- 结果：MCP 服务器当前未连通。
- 工具：api_probe
"""
    out = _drop_stale_entries(md)
    assert "做了什么" not in out, "留下了没有结论的残缺条目"
    assert "api_probe" not in out
    assert "查许可证" not in out


def test_empty_and_headerless_input_is_safe():
    """空输入与无 `## ` 标题的输入不得炸，也不得丢掉正文。"""
    assert _drop_stale_entries("") == ""
    plain = "# 只有标题\n没有任何条目"
    assert _drop_stale_entries(plain) == plain


def test_head_before_first_entry_is_preserved():
    """首个 `## ` 之前的文件头必须保留。"""
    md = "# 2026-09-09 工作日志\n\n## 条目（00:01）\n- 结果：未连通。\n"
    out = _drop_stale_entries(md)
    assert "# 2026-09-09 工作日志" in out
    assert "未连通" not in out
