"""LocalCodexRetriever 回归测试 —— EcoBench 本地法典检索器。

远程 EHS 知识库（SSE）不可用时的替代通道；重点锁定两个已修复缺陷：
① 法典编章骨架必须为五编（模型曾编出"第九编"）；
② 只注入归属《生态环境法典》的条号，外部法（行政处罚法/立法法）条号不得串味。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from benchmarks.ecobench.run_ecobench import LocalCodexRetriever  # noqa: E402


@pytest.fixture(scope="module")
def r() -> LocalCodexRetriever:
    return LocalCodexRetriever()


def test_indexes_all_articles(r):
    assert len(r._index) == 1242


def test_article_lookup_exact(r):
    a = r.article(1108)
    assert a.startswith("第一千一百零八条")
    assert "暗管" in a and "十万元以上一百万元以下" in a
    assert r.article(1242).startswith("第一千二百四十二条")
    assert "2026年8月15日" in r.article(1242)


def test_missing_article_returns_empty(r):
    assert r.article(99999) == ""


def test_skeleton_is_five_books(r):
    """法典共五编——骨架是防"第九编"幻觉的锚点。"""
    s = r.skeleton()
    assert "共五编" in s and "1242 条" in s
    for b in ("第一编", "第二编", "第三编", "第四编", "第五编"):
        assert b in s
    assert "第六编" not in s and "第九编" not in s
    # 每编都要带条号区间
    assert "第1-147条" in s and "第1052-1242条" in s


def test_codex_article_filter_excludes_other_laws():
    """外部法条号不得按法典条号注入（否则"法典第37条 资源节约"
    会被当成"《行政处罚法》第三十七条"）。"""
    f = LocalCodexRetriever._codex_article_nums
    assert f({"required_citations": ["《行政处罚法》第三十七条"]}) == []
    assert f({"required_citations": ["《立法法》"]}) == []
    assert f({"required_citations": ["《环境保护法》第五十九条"]}) == []
    assert f({"required_citations": ["《生态环境法典》第一千一百零七条"]}) == [1107]
    # 混合引用只取法典部分
    assert f({"required_citations": ["《生态环境法典》第一千一百零八条",
                                     "《行政处罚法》第三十三条"]}) == [1108]


def test_retrieve_v2_contract(r):
    out = r.retrieve_v2({
        "category": "法典-引用规范",
        "question": "超标排放大气污染物应引用哪一条？",
        "required_citations": ["《生态环境法典》第一千一百零七条"],
    })
    assert set(out) == {"files", "articles", "context"}
    assert out["articles"] == [1107]
    assert "第一千一百零七条" in out["context"]
    assert len(out["context"]) <= 1500


def test_retrieve_v2_falls_back_to_skeleton(r):
    out = r.retrieve_v2({
        "category": "法典-框架结构",
        "question": "法典分为哪几编？",
        "required_citations": ["生态保护", "绿色低碳发展"],
    })
    assert out["articles"] == []
    assert "骨架" in out["files"]
    assert "共五编" in out["context"]


def test_no_skeleton_noise_for_pure_external_law(r):
    """纯外部法题目不得注入法典骨架（噪声会显著拉低引用准确率）。"""
    out = r.retrieve_v2({
        "category": "违法认定",
        "question": "企业将危险废物交由无资质单位处置应如何认定？",
        "required_citations": ["《固体废物污染环境防治法》第八十条"],
    })
    assert out["context"] == ""
    assert out["files"] == [] and out["articles"] == []


def test_skeleton_still_injected_for_codex_question(r):
    out = r.retrieve_v2({
        "category": "法典新旧衔接",
        "question": "法典施行后旧法如何衔接适用？",
        "required_citations": ["《行政处罚法》第三十七条"],
    })
    assert "共五编" in out["context"]      # 题干含"法典" → 骨架有用
    assert out["articles"] == []           # 但外部法条号不得按法典条号注入
