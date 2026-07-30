#!/usr/bin/env python3
"""
test_ecobench_norm.py — 评分器条款号中文数字归一化测试（离线）

覆盖：
  - cn_to_int / normalize_cn_numerals 的等价转换
  - score_item 归一化后命中（"第99条" vs 金标准 "第九十九条"）
  - 归一化前后分数对照字段（*_raw）
  - 诚实性：全错答案必须仍为 0 分
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from benchmarks.ecobench.run_ecobench import (  # noqa: E402
    _norm,
    cn_to_int,
    extract_article_nums,
    extract_law_names,
    normalize_cn_numerals,
    score_item,
)

ITEM = {
    "id": "EB01", "category": "法条引用",
    "question": "企业向大气超标排放污染物，应依据哪条查处？",
    "required_citations": ["《大气污染防治法》第九十九条"],
    "key_points": ["大气污染防治法", "第九十九条", "超标排放"],
}


def test_cn_to_int():
    assert cn_to_int("九十九") == 99
    assert cn_to_int("三十一") == 31
    assert cn_to_int("八十四") == 84
    assert cn_to_int("一百一十二") == 112
    assert cn_to_int("十") == 10
    assert cn_to_int("99") == 99
    assert cn_to_int("") is None


def test_normalize_cn_numerals_article_forms():
    assert normalize_cn_numerals("第九十九条") == "第99条"
    assert normalize_cn_numerals("第99条") == "第99条"
    assert normalize_cn_numerals("九十九") == "99"
    assert "第99条" in _norm("《大气污染防治法》第九十九条")


def test_score_item_arabic_answer_hits_hanzi_gold():
    """答案用阿拉伯数字条款号，金标准用汉字数字：归一化后必须命中"""
    sc = score_item("应依据《大气污染防治法》第99条，超标排放责令改正。", ITEM)
    assert sc["citation_hit"] == 1.0
    assert sc["citation_hit_raw"] == 0.0   # 归一化前不命中，形成对照
    assert sc["keypoint_f1"] > sc["keypoint_f1_raw"]


def test_score_item_hanzi_answer_hits_as_before():
    sc = score_item("应依据《大气污染防治法》第九十九条处理，超标排放。", ITEM)
    assert sc["citation_hit"] == 1.0
    assert sc["citation_hit_raw"] == 1.0


def test_score_item_wrong_answer_still_zero():
    """诚实性：全错答案归一化后仍必须 0 分"""
    sc = score_item("随便回答，与题目毫无关系。", ITEM)
    assert sc["citation_hit"] == 0.0
    assert sc["keypoint_f1"] == 0.0
    assert sc["citation_hit_raw"] == 0.0


def test_score_item_wrong_article_number_not_overcredited():
    """归一化不得把错误条款号误判为命中"""
    sc = score_item("应依据《大气污染防治法》第98条处理。", ITEM)
    assert sc["citation_hit"] == 0.0


def test_extract_law_names_and_articles():
    assert extract_law_names(ITEM) == ["大气污染防治法"]
    assert extract_article_nums(ITEM) == [99]
    assert extract_law_names({"required_citations": [], "question": "噪声扰民如何处罚？"}) \
        == ["噪声污染防治法"]
