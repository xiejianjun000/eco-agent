#!/usr/bin/env python3
"""tests/modules/test_artifact_discovery.py — 产物必须在两个落点都能被发现

真实缺陷（本次实测抓到，不是假想）：

  用户要求「写成简报并落盘 md 文件」，模型正常调了 save_document 并成功
  返回 {"saved": true, "path": ".../eco-agent/output/xxx.md"}，
  但右栏产物面板数量始终不变，/documents 也看不到。

  根因是三处口径不一致：
    · save_document 工具   → 落到 output/*.md
    · list_documents.files → 只收 output/ 里的 .docx/.pptx/.xlsx/.pdf，
                             .md 被后缀过滤排除
    · list_documents.artifacts → 只收 ~/.eco/artifacts/*.md

  于是 output/*.md 两边都不收，成了黑洞 —— 实测有 30 个 .md 一直不可见，
  最新一个停留在两天前。模型把活干完了，用户看不到成果。

  这类缺陷的教训：不能因为「工具返回 saved: true」就认为链路通了。
  存了 ≠ 看得到，落点与展示口径必须逐一对齐。

同时锁死：列出来的产物必须能读能下载。此前 read_artifact / download_artifact
也只查 ~/.eco/artifacts/，就算列表修好了，点开仍会 404。
"""

from __future__ import annotations

import importlib


def _reload_documents(monkeypatch, eco_dir, output_dir):
    """按给定目录重载 documents 模块（OUTPUT_DIR 是模块级常量）。"""
    monkeypatch.setenv("ECO_DIR", str(eco_dir))
    import server.api.documents as doc

    importlib.reload(doc)
    monkeypatch.setattr(doc, "OUTPUT_DIR", output_dir)
    return doc


def test_md_in_output_dir_is_discovered(tmp_path, monkeypatch):
    """save_document 落到 output/*.md 必须能被列出——本次缺陷的核心。"""
    eco, out = tmp_path / "eco", tmp_path / "output"
    (eco / "artifacts").mkdir(parents=True)
    out.mkdir()
    (out / "简报.md").write_text("# 简报", encoding="utf-8")

    doc = _reload_documents(monkeypatch, eco, out)
    import asyncio

    r = asyncio.run(doc.list_documents())
    names = [a["name"] for a in r["artifacts"]]
    assert "简报.md" in names, f"output/*.md 未被发现：{names}"


def test_both_roots_are_merged(tmp_path, monkeypatch):
    """两个落点的产物都要收，不能只收一边。"""
    eco, out = tmp_path / "eco", tmp_path / "output"
    art = eco / "artifacts"
    art.mkdir(parents=True)
    out.mkdir()
    (art / "完整稿.md").write_text("A", encoding="utf-8")
    (out / "工具存的.md").write_text("B", encoding="utf-8")

    doc = _reload_documents(monkeypatch, eco, out)
    import asyncio

    names = {a["name"] for a in asyncio.run(doc.list_documents())["artifacts"]}
    assert names == {"完整稿.md", "工具存的.md"}, names


def test_same_name_is_deduped(tmp_path, monkeypatch):
    """同名文件只出现一次，避免右栏出现重复条目。"""
    eco, out = tmp_path / "eco", tmp_path / "output"
    art = eco / "artifacts"
    art.mkdir(parents=True)
    out.mkdir()
    (art / "同名.md").write_text("A", encoding="utf-8")
    (out / "同名.md").write_text("B", encoding="utf-8")

    doc = _reload_documents(monkeypatch, eco, out)
    import asyncio

    names = [a["name"] for a in asyncio.run(doc.list_documents())["artifacts"]]
    assert names.count("同名.md") == 1, f"同名未去重：{names}"


def test_sorted_by_mtime_desc(tmp_path, monkeypatch):
    """合并后必须整体按时间倒序——两个目录各自有序，拼接后未必有序。"""
    import os
    import time

    eco, out = tmp_path / "eco", tmp_path / "output"
    art = eco / "artifacts"
    art.mkdir(parents=True)
    out.mkdir()
    (art / "旧.md").write_text("old", encoding="utf-8")
    (out / "新.md").write_text("new", encoding="utf-8")
    now = time.time()
    os.utime(art / "旧.md", (now - 9000, now - 9000))
    os.utime(out / "新.md", (now, now))

    doc = _reload_documents(monkeypatch, eco, out)
    import asyncio

    names = [a["name"] for a in asyncio.run(doc.list_documents())["artifacts"]]
    assert names[0] == "新.md", f"未按时间倒序：{names}"


def test_listed_artifact_can_be_read(tmp_path, monkeypatch):
    """列出来就必须读得到——否则点开预览 404。"""
    eco, out = tmp_path / "eco", tmp_path / "output"
    (eco / "artifacts").mkdir(parents=True)
    out.mkdir()
    (out / "可读.md").write_text("# 正文内容", encoding="utf-8")

    doc = _reload_documents(monkeypatch, eco, out)
    import asyncio

    r = asyncio.run(doc.read_artifact("可读.md"))
    assert r["content"] == "# 正文内容"


def test_path_traversal_is_rejected(tmp_path, monkeypatch):
    """只取 basename，绝不允许穿越——入参来自前端/模型。"""
    import asyncio

    from fastapi import HTTPException

    eco, out = tmp_path / "eco", tmp_path / "output"
    (eco / "artifacts").mkdir(parents=True)
    out.mkdir()
    (tmp_path / "secret.md").write_text("机密", encoding="utf-8")

    doc = _reload_documents(monkeypatch, eco, out)
    for evil in ("../secret.md", "../../secret.md", "/etc/passwd"):
        try:
            asyncio.run(doc.read_artifact(evil))
            raise AssertionError(f"未拦截穿越：{evil}")
        except HTTPException as e:
            assert e.status_code == 404


def test_missing_dirs_do_not_crash(tmp_path, monkeypatch):
    """目录不存在时返回空列表，不得抛异常。"""
    eco, out = tmp_path / "nope", tmp_path / "nada"
    doc = _reload_documents(monkeypatch, eco, out)
    import asyncio

    r = asyncio.run(doc.list_documents())
    assert r["artifacts"] == [] and r["count"] == 0
