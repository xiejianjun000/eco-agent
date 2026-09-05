"""冒烟测试：不依赖外部网络的单元级验证。

覆盖：配置栏目表完整性、URL 构造、详情页正则、HTML 列表解析、空气数据归一化。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hunan_env_mcp import config  # noqa: E402
from hunan_env_mcp.datasource import web_crawler  # noqa: E402
from hunan_env_mcp.datasource.air_api import _normalize_rows  # noqa: E402


def test_channels_complete():
    assert config.CHANNELS["notice"]["mode"] == "api"
    assert len(config.CHANNELS["notice"]["api_ids"]) == 2
    assert config.CHANNELS["eia_accept"]["path"].endswith("jsslgk")
    assert config.CHANNELS["policy"]["path"].endswith("gfxwj")
    assert len(config.CHANNELS) >= 12


def test_list_url_pattern():
    # 分页 URL 规律：index.html / index_N.html
    def build(path: str, page: int) -> str:
        suffix = "index.html" if page <= 1 else f"index_{page}.html"
        return f"{config.BASE_URL}/sthjt/{path.strip('/')}/{suffix}"

    assert build("xxgk/tzgg", 1) == "https://sthjt.hunan.gov.cn/sthjt/xxgk/tzgg/index.html"
    assert build("xxgk/tzgg", 2) == "https://sthjt.hunan.gov.cn/sthjt/xxgk/tzgg/index_2.html"


def test_detail_url_regex():
    pat = re.compile(config.DETAIL_RE_PATTERN)
    assert pat.search("https://sthjt.hunan.gov.cn/sthjt/xxgk/tzgg/gg/202608/t20260826_34051299.html")
    assert not pat.search("https://sthjt.hunan.gov.cn/sthjt/xxgk/tzgg/index.html")


def test_html_list_parsing():
    html = """
    <ul>
      <li><span>2026-08-26</span><a href="/sthjt/xxgk/tzgg/gg/202608/t20260826_34051299.html">关于某事项的公告</a></li>
      <li><span>2026-08-25</span><a href="/sthjt/xxgk/tzgg/gg/202608/t20260825_34051298.html">关于另一事项的通知</a></li>
      <li><a href="/sthjt/xxgk/tzgg/index.html">返回列表</a></li>
    </ul>
    """
    # 通过真实抓取路径解析本地片段：模拟 fetch_html 返回
    orig_fetch = web_crawler.fetch_html
    web_crawler.fetch_html = lambda url, **kw: html  # type: ignore[assignment]
    try:
        items = web_crawler._list_html("xxgk/tzgg/gg", "index", page=1)
    finally:
        web_crawler.fetch_html = orig_fetch  # type: ignore[assignment]

    assert len(items) == 2, items
    assert items[0]["title"] == "关于某事项的公告"
    assert items[0]["date"] == "2026-08-26"
    assert items[0]["url"].endswith("t20260826_34051299.html")


def test_normalize_rows():
    assert _normalize_rows([{"AQI": 26}]) == [{"AQI": 26}]
    assert _normalize_rows({"data": [{"AQI": 30}]}) == [{"AQI": 30}]
    assert _normalize_rows({"data": None}) == []
    assert _normalize_rows("bad") == []


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
        print(f"PASS {fn.__name__}")
    print("all smoke tests passed")
