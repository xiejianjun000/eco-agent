"""eia-router 调度手册测试。

对标 WorkBuddy ardot-design-router 的结构：决策树 + 硬规则 + 兜底反问。

这个 Router 存在的理由是实测踩出来的：
  1. 四台服务器检索词参数名不一致（name / keyword / query），
     传错直接 1 validation error
  2. 模型曾据返回数据里的 hpyDetailUrl 臆造 get_hpy_detail 工具
  3. 限值只报数字而不带适用条件是有害的（新建/现有、炉型、地区各不同）
"""
import asyncio
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
SKILL = REPO / "ecoskills" / "eia-router" / "SKILL.md"


def _body() -> str:
    return SKILL.read_text(encoding="utf-8")


def test_skill_exists_and_loads():
    from server.api.chat import _run_tool
    r = json.loads(asyncio.run(_run_tool("use_skill", {"name": "eia-router"})))
    assert r["ok"] is True
    assert len(r["content"]) > 1000


def test_visible_in_skill_list():
    """必须出现在清单里，否则模型发现不了。"""
    from server.api.chat import _run_tool
    d = json.loads(asyncio.run(_run_tool("use_skill", {"list": True})))
    assert "eia-router" in {s["name"] for s in d["skills"]}


def test_covers_all_eleven_tools():
    """11 个工具必须全部出现在手册里，漏一个就等于没挂。"""
    from tests.modules.test_eia_mcp import EIA_TOOLS
    body = _body()
    missing = [t for t in EIA_TOOLS if t.split("__")[-1] not in body]
    assert not missing, f"手册未覆盖: {missing}"


def test_documents_all_three_param_names():
    """三套参数名必须写清楚 —— 这是最容易出错的地方。"""
    body = _body()
    for p in ("`name`", "`query`", "`keyword`"):
        assert p in body, f"缺少参数名说明: {p}"
    assert "Unexpected keyword argument" in body, "应写明传错参数的真实报错"


def test_forbids_hallucinated_tool():
    """必须明写禁止臆造详情工具 —— 实测发生过。"""
    body = _body()
    assert "hpyDetailUrl" in body
    assert "get_hpy_detail" in body


def test_has_unclear_fallback():
    """对标 WorkBuddy：分类不出来要反问，不能瞎猜。"""
    body = _body()
    assert "判断不了" in body or "无法归入" in body
    assert "反问" in body


def test_limit_must_carry_conditions():
    """限值只报数字是有害的，手册必须要求带适用条件。"""
    body = _body()
    for kw in ("标准号", "适用条件", "基准氧含量"):
        assert kw in body, f"限值规则缺少: {kw}"


def test_local_stricter_than_national_rule():
    """地方常严于国标，只报国标会给出偏松结论。"""
    body = _body()
    assert "地方" in body and "国标" in body
    assert re.search(r"地方.{0,12}严于|严于.{0,12}国", body), "应写明地方可能严于国家"


def test_frontmatter_valid():
    body = _body()
    m = re.match(r"^---\n(.*?)\n---", body, re.S)
    assert m, "缺少 frontmatter"
    fm = m.group(1)
    assert "name: eia-router" in fm
    assert "description:" in fm
    # 这是调度器，必须允许模型自主加载
    assert "disable-model-invocation: true" not in fm
