"""质量门禁（DSH guard 对标）单测：条号↔内容一致性 / 表格行数一致性。"""
from server.api.chat import _quality_gate


def test_gate_catches_wrong_citation():
    # 引用内容与法典原文零重合 → 触发纠偏
    needs, note = _quality_gate("✅ 第1107条：个人未批先建处十五日以下拘留。", [])
    assert needs is True
    assert "第1107条" in note and "不一致" in note


def test_gate_passes_correct_citation():
    # 正确引用（10万-100万与原文一致）→ 静默通过
    needs, note = _quality_gate("✅ 第1107条：超标排放处十万元以上一百万元以下罚款。", [])
    assert needs is False and note == ""


def test_gate_table_row_count():
    # '共9个' vs 表格 2 行 → 触发
    needs, note = _quality_gate("资江共 9 个断面。\n| a | b |\n|---|---|\n| 1 | x |\n| 2 | y |", [])
    assert needs is True
    assert "表格行数" in note


def test_gate_ok_table():
    # 行数相符 → 通过
    text = ("共 2 个断面。\n| a | b |\n|---|---|\n| 1 | x |\n| 2 | y |")
    needs, _ = _quality_gate(text, [])
    assert needs is False


def test_gate_nonexistent_article_skipped():
    # 不存在的条号（如9999）由工具链兜底，门禁不误报
    needs, note = _quality_gate("第9999条不存在。", [])
    assert needs is False


# ─── 交互图表卡片提取 ───
from server.api.chat import _extract_cards


def test_extract_cards_replaces_block():
    text = ("✅ 趋势如下：\n```card\n<title>PM2.5趋势</title>\n"
            "<div id='c'></div><script>echarts.init(c)</script>\n```\n要点：全部达标")
    out, cards = _extract_cards(text)
    assert "```card" not in out
    assert "📊 PM2.5趋势" in out
    assert len(cards) == 1
    assert cards[0]["title"] == "PM2.5趋势"
    assert "echarts" in cards[0]["html"]
    assert "<title>" not in cards[0]["html"]


def test_extract_cards_no_block():
    text = "普通回答无卡片"
    out, cards = _extract_cards(text)
    assert out == text and cards == []


# ─── 「详细版」承诺兑现 ───
from agent_core import full_replies as fr


def test_full_replies_save_and_get(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "STORE", tmp_path / "fr.jsonl")
    monkeypatch.setattr(fr, "_TTL", 3600)
    fr.save_full("要点版（截断）", "完整原稿" * 100)
    got = fr.get_full("回复详细版")
    assert got and got.startswith("完整原稿")
    # 非请求消息不命中
    assert fr.get_full("查一下第45条") is None


def test_full_replies_too_short_not_saved(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "STORE", tmp_path / "fr2.jsonl")
    fr.save_full("截断稿", "截断稿加一点点")
    assert fr.get_full("详细版") is None
