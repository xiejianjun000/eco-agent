"""湖南省厅环境质量月报工具测试：表格解析 / 文章定位 / 关键词过滤（mock 网络）。"""

from govmcp_tools import hunan_env as he

SAMPLE_HTML = """
<html><body>
<li><a title='2026年7月全省环境质量状况' target="_blank"
   href="/sthjt/xxgk/zdly/hjjc/hjzl/202608/t20260819_34047353.html"><span><img src="/x.png"></span></a></li>
<li><a title='2026年6月全省环境质量状况' target="_blank"
   href="/sthjt/xxgk/zdly/hjjc/hjzl/202607/t20260720_34029906.html"><span><img></span></a></li>
<table>
<tr><th>序号</th><th>市州</th><th>县市区</th><th>流域</th><th>断面</th><th>水质类别</th></tr>
<tr><td>205</td><td>娄底市</td><td>冷水江市</td><td>资江流域</td><td>晓云渡口</td><td>Ⅱ类</td></tr>
<tr><td>206</td><td>娄底市</td><td>涟源市</td><td>资江流域</td><td>某某渡口</td><td>Ⅲ类</td></tr>
</table>
</body></html>
"""


def test_parse_tables_keyword_filter():
    rows, n = he._parse_tables(SAMPLE_HTML, keyword="冷水江")
    assert n == 1
    assert rows[0][:3] == ["205", "娄底市", "冷水江市"]
    assert "Ⅱ类" in rows[0]


def test_parse_tables_all_rows():
    rows, n = he._parse_tables(SAMPLE_HTML, keyword="")
    # 表头行 + 两数据行（表格内全部行）
    assert n >= 2
    joined = " ".join(" ".join(r) for r in rows)
    assert "冷水江市" in joined and "涟源市" in joined


def test_find_article_title_attr(monkeypatch):
    monkeypatch.setattr(he, "_fetch", lambda url, timeout=15.0: SAMPLE_HTML)
    hit = he._find_article(2026, 7)
    assert hit is not None
    url, title = hit
    assert title == "2026年7月全省环境质量状况"
    assert url.endswith("t20260819_34047353.html")
    assert url.startswith("https://sthjt.hunan.gov.cn")


def test_find_article_missing(monkeypatch):
    monkeypatch.setattr(he, "_fetch", lambda url, timeout=15.0: "<html>无数据</html>")
    assert he._find_article(2026, 12) is None


def test_gunzip_guard():
    # 服务端声明 gzip 但未压缩时不解压、不报错；真 gzip 正确解压
    import gzip

    raw = "你好".encode()
    assert he._maybe_gunzip(raw, "gzip") == raw
    assert he._maybe_gunzip(gzip.compress(raw), "gzip") == raw
    assert he._maybe_gunzip(gzip.compress(raw), "identity") == gzip.compress(raw)
