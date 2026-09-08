"""jiance-guifan 技能回归测试 —— 监测技术规范清单知识库与检索脚本。

覆盖：知识库完整性（209 项标准 / 8 份法规 205 条）、检索脚本四类查询、
原件字形缺陷修复点、evals 套件引用真实性。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SKILL = ROOT / "ecoskills" / "jiance-guifan"
KB = SKILL / "kb"
LOOKUP = SKILL / "scripts" / "lookup.py"


def run(*args: str) -> dict:
    r = subprocess.run([sys.executable, str(LOOKUP), *args],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


# ---------------------------------------------------------------- 知识库
def test_skill_files_exist():
    assert (SKILL / "SKILL.md").exists()
    assert (SKILL / "manifest.json").exists()
    assert LOOKUP.exists()
    for f in ("监测技术规范清单_结构化.json", "监测配套法规全文.json",
              "标准号索引.json", "学习题库.json"):
        assert (KB / f).exists(), f


def test_catalog_completeness():
    data = json.loads((KB / "监测技术规范清单_结构化.json").read_text(encoding="utf-8"))
    assert data["total"] == 209
    items = data["items"]
    assert len(items) == 209
    # 每条必须有名称 / 标准号 / 发布日期 / 溯源页码
    for x in items:
        assert x["name"] and x["code"] and x["issued"] and x["source_page"]


def test_catalog_section_numbering_contiguous():
    """各分节序号必须 1..N 连续——抽取漏条的直接探针。"""
    from collections import defaultdict
    items = json.loads((KB / "监测技术规范清单_结构化.json").read_text(encoding="utf-8"))["items"]
    groups = defaultdict(list)
    for x in items:
        groups[(x["part"], x["section"])].append(x["seq_in_section"])
    for key, nums in groups.items():
        assert sorted(nums) == list(range(1, len(nums) + 1)), key


def test_appendix_articles():
    docs = json.loads((KB / "监测配套法规全文.json").read_text(encoding="utf-8"))
    assert len(docs) == 8
    by_title = {d["title"]: d for d in docs}
    assert by_title["生态环境监测条例"]["articles"] == 49
    assert by_title["检验检测机构资质认定管理办法"]["articles"] == 40
    assert by_title["检验检测机构监督管理办法"]["articles"] == 29
    assert by_title["环境监测数据弄虚作假行为判定及处理办法"]["articles"] == 18


def test_glyph_defect_articles_restored():
    """原 PDF 中被字形缺陷吞掉的三个条号必须已还原且正文非空。"""
    for doc, art, kw in (
        ("生态环境监测条例", "31", "运行维护记录制度"),
        ("生态环境监测条例", "41", "依法给予处分"),
        ("检验检测机构监督管理办法", "21", "职权"),
    ):
        res = run("law", doc, art)
        assert "error" not in res, res
        assert kw in res["text"], (doc, art, res["text"][:80])


# ---------------------------------------------------------------- 检索
def test_lookup_std_exact():
    """完整标准号精确命中；不含年份的前缀走 prefix 匹配。"""
    res = run("std", "HJ 91.2-2022")
    assert res["match"] == "exact" and res["count"] == 1
    assert res["results"][0]["name"] == "地表水环境质量监测技术规范"

    pre = run("std", "HJ 91.2")
    assert pre["match"] == "prefix" and pre["count"] == 1


def test_lookup_std_missing_returns_zero():
    """虚构标准号必须查无——反幻觉底线。"""
    res = run("std", "HJ 99999-2099")
    assert res["count"] == 0


def test_lookup_search_and_medium():
    assert run("search", "地下水")["count"] >= 4
    assert run("medium", "水和废水")["count"] == 28


def test_lookup_nav_totals():
    nav = run("nav")
    assert nav["total"] == 209
    assert sum(v["count"] for v in nav["tree"].values()) == 209


def test_lookup_law_penalty_article():
    """条例第45条（技术服务机构造假）罚则必须可直查。"""
    res = run("law", "生态环境监测条例", "45")
    assert "10 万元以上50 万元以下" in res["text"].replace("\u3000", " ")
    assert "200" in res["text"]


def test_lookup_lawsearch():
    res = run("lawsearch", "弄虚作假")
    assert res["count"] > 10


def test_stats_selfconsistent():
    s = run("stats")
    assert s["标准条目"] == 209
    assert sum(s["按要素"].values()) == 209
    assert sum(s["按序列"].values()) == 209


# ---------------------------------------------------------------- 题库 / evals
def test_quiz_bank():
    q = json.loads((KB / "学习题库.json").read_text(encoding="utf-8"))
    assert q["total"] >= 400
    for x in q["items"]:
        assert x["question"] and x["answer_key"] and x["reference"]


@pytest.mark.parametrize("suite", ["jiance-standards", "jiance-laws"])
def test_eval_suites_exist(suite):
    p = ROOT / "evals" / f"{suite}.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert text.count("## Q") >= 200
    assert "引用校验:" in text
