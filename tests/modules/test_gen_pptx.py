#!/usr/bin/env python3
"""
tests/modules/test_gen_pptx.py — 纯标准库 PPTX 生成器测试

覆盖: 结构合法性（OOXML 必需部件）、多页、XML 转义（防注入）、CLI。
"""

import io
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.gen_pptx import build_pptx  # noqa: E402


def _parse(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def test_minimal_structure():
    data = build_pptx([{"title": "标题", "bullets": ["要点1", "要点2"]}])
    z = _parse(data)
    names = z.namelist()
    for required in ("[Content_Types].xml", "_rels/.rels",
                     "ppt/presentation.xml", "ppt/slides/slide1.xml"):
        assert required in names, f"缺部件: {required}"


def test_multi_page():
    slides = [{"title": f"第{i}页", "bullets": ["a", "b"]} for i in range(5)]
    data = build_pptx(slides)
    z = _parse(data)
    for i in range(1, 6):
        assert f"ppt/slides/slide{i}.xml" in z.namelist()
    pres = z.read("ppt/presentation.xml").decode()
    assert pres.count("<p:sldId ") == 5


def test_xml_escape():
    """标题含 XML 特殊字符必须转义（防 XML 注入/损坏）。"""
    data = build_pptx([{"title": "a<b>&\"c", "bullets": []}])
    z = _parse(data)
    slide = z.read("ppt/slides/slide1.xml").decode()
    assert "<b>&amp;" in slide or "&lt;b&gt;" in slide


def test_cli_quick_mode(tmp_path):
    import subprocess

    out = tmp_path / "quick.pptx"
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_pptx.py"),
                        str(out), "--title", "快速模式", "--bullets", "甲|乙|丙"],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert out.exists()
    z = zipfile.ZipFile(out)
    slide = z.read("ppt/slides/slide1.xml").decode()
    assert "快速模式" in slide and "甲" in slide and "丙" in slide
