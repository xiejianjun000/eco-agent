#!/usr/bin/env python3
"""
docx_gen.py — 纯标准库 Markdown → DOCX 生成器（零第三方依赖）

WorkBuddy 文档路由对标：结构化文书/报告在用户提到 DOCX/Word 时落盘为
.docx（默认仍是 MD）。docx 本质是 zip 包，这里用 zipfile + XML 手写
最小但完整可打开的 Word 文档（标题/段落/列表/表格/代码块/引用）。

结构：[Content_Types].xml + _rels/.rels + word/document.xml +
word/_rels/document.xml.rels + word/styles.xml
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

_XML_ESCAPE = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def _esc(text: str) -> str:
    return "".join(_XML_ESCAPE.get(c, c) for c in (text or ""))


def _para(runs: str, style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{runs}</w:p>"


def _run(text: str, bold: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:r>{rpr}<w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'


def _table(headers: list[str], rows: list[list[str]]) -> str:
    """markdown 表格 → w:tbl（带边框 + 表头底纹）。"""
    body: list[str] = []
    all_rows = [headers] + rows
    for ri, row in enumerate(all_rows):
        body.append("<w:tr>")
        for cell in row:
            shade = '<w:shd w:val="clear" w:fill="D9E2F3"/>' if ri == 0 else ""
            body.append(
                f'<w:tc><w:tcPr>{shade}</w:tcPr>'
                f'{_para(_run(cell.strip()), style="Normal")}</w:tc>')
        body.append("</w:tr>")
    return (
        "<w:tbl><w:tblPr>"
        '<w:tblBorders>'
        '<w:top w:val="single" w:sz="4" w:color="999999"/>'
        '<w:left w:val="single" w:sz="4" w:color="999999"/>'
        '<w:bottom w:val="single" w:sz="4" w:color="999999"/>'
        '<w:right w:val="single" w:sz="4" w:color="999999"/>'
        '<w:insideH w:val="single" w:sz="4" w:color="999999"/>'
        '<w:insideV w:val="single" w:sz="4" w:color="999999"/>'
        "</w:tblBorders></w:tblPr>"
        + "".join(body) + "</w:tbl>")


def md_to_docx_bytes(md: str) -> bytes:
    """把 Markdown 文本渲染为 DOCX 字节流。"""
    body: list[str] = []
    lines = (md or "").splitlines()
    i = 0
    in_code = False
    code_buf: list[str] = []

    def flush_code():
        nonlocal code_buf
        if code_buf:
            for cl in code_buf:
                body.append(_para(_run(cl), style="CodeBlock"))
            code_buf = []

    while i < len(lines):
        line = lines[i].rstrip()
        t = line.strip()
        if t.startswith("```"):
            if in_code:
                in_code = False
                flush_code()
            else:
                flush_code()
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", t)
        if m:
            level = min(len(m.group(1)), 2)
            style = "Heading1" if level == 1 else "Heading2"
            body.append(_para(_run(m.group(2)), style=style))
            i += 1
            continue
        if t.startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1]):
            headers = [c.strip() for c in t.strip("|").split("|")]
            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            body.append(_table(headers, rows))
            i = j
            continue
        if re.match(r"^[-*•]\s+", t):
            body.append(_para(_run(re.sub(r"^[-*•]\s+", "", t)), style="ListParagraph"))
            i += 1
            continue
        m = re.match(r"^\d+[.)]\s+(.*)$", t)
        if m:
            body.append(_para(_run(m.group(1)), style="ListParagraph"))
            i += 1
            continue
        if t.startswith(">"):
            body.append(_para(_run(t.lstrip("> ")), style="Quote"))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})$", t):
            body.append(_para(_run("─" * 20)))
            i += 1
            continue
        if not t:
            i += 1
            continue
        body.append(_para(_run(t)))
        i += 1
    flush_code()
    body.append('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
                '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>')

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(body)}</w:body></w:document>")

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        "</Types>")

    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>')

    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/></Relationships>')

    styles_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
        '<w:rPr><w:sz w:val="21"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
        '<w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>'
        '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>'
        '<w:pPr><w:spacing w:before="200" w:after="80"/></w:pPr>'
        '<w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/>'
        '<w:pPr><w:ind w:left="360"/></w:pPr><w:rPr><w:sz w:val="21"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="CodeBlock"><w:name w:val="Code Block"/>'
        '<w:pPr><w:ind w:left="360"/></w:pPr>'
        '<w:rPr><w:rFonts w:ascii="Courier New" w:hAnsi="Courier New"/><w:sz w:val="18"/></w:rPr></w:style>'
        '<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/>'
        '<w:pPr><w:ind w:left="360"/></w:pPr><w:rPr><w:i/><w:sz w:val="21"/></w:rPr></w:style>'
        "</w:styles>")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/_rels/document.xml.rels", doc_rels)
        z.writestr("word/styles.xml", styles_xml)
    return buf.getvalue()


def save_md_as_docx(md: str, path: str | Path) -> str:
    """把 Markdown 文本落盘为 .docx，返回路径。"""
    p = Path(path)
    if p.suffix.lower() != ".docx":
        p = p.with_suffix(".docx")
    p.write_bytes(md_to_docx_bytes(md))
    return str(p)


# ===== 自测 =====

def test():
    import tempfile

    md = """# 冷水江市执法建议书

## 一、案件概况

- 当事人：某排污企业
- 违法行为：超标排放水污染物

## 二、法律依据

| 条款 | 内容 |
|------|------|
| 第1054条 | 超标排放的处罚依据 |

> 依据《生态环境法典》第 1054 条。

```python
print("证据链完整")
```
"""
    data = md_to_docx_bytes(md)
    assert data[:2] == b"PK", "必须是 zip 包"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        assert "word/document.xml" in names and "[Content_Types].xml" in names
        xml = z.read("word/document.xml").decode("utf-8")
        for probe in ("执法建议书", "案件概况", "第1054条", "超标排放"):
            assert probe in xml, f"缺 {probe}"
    tmp = Path(tempfile.mkdtemp()) / "建议书.docx"
    save_md_as_docx(md, tmp)
    print("生成:", tmp, tmp.stat().st_size, "bytes")
    print("包内:", zipfile.ZipFile(tmp).namelist())
    print("[OK] docx_gen 自测通过")


if __name__ == "__main__":
    test()
