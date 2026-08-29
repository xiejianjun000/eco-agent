#!/usr/bin/env python3
"""
server/api/documents.py — 文档面板 API

右侧栏"文档"页数据源：output/ 目录文件列表 + MCP-Doc（腾讯 Word 处理）工具清单。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("eco.server.documents")

router = APIRouter()

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"


def _artifacts_dir() -> Path:
    """回答产物目录（$ECO_DIR/artifacts/，与 chat._save_answer_artifact 一致）。"""
    base = Path(os.environ.get("ECO_DIR") or Path.home() / ".eco")
    return base / "artifacts"


@router.get("/documents")
async def list_documents() -> dict:
    files = []
    if OUTPUT_DIR.is_dir():
        for f in sorted(OUTPUT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file() and f.suffix.lower() in (".docx", ".pptx", ".xlsx", ".pdf"):
                st = f.stat()
                files.append({
                    "name": f.name,
                    "path": str(f),
                    "size_kb": round(st.st_size / 1024, 1),
                    "modified": st.st_mtime,
                })
    # 回答产物（MD）并入文档列表：持久落盘，重启仍在
    art_dir = _artifacts_dir()
    artifacts = []
    if art_dir.is_dir():
        for f in sorted(art_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            st = f.stat()
            artifacts.append({
                "name": f.name,
                "path": str(f),
                "size_kb": round(st.st_size / 1024, 1),
                "modified": st.st_mtime,
                "kind": "artifact",
            })
    return {"count": len(files) + len(artifacts), "files": files, "artifacts": artifacts}


@router.get("/documents/artifact/{name}")
async def read_artifact(name: str) -> dict:
    """返回回答产物的 Markdown 原文（前端点开产物卡片时拉取渲染）。"""
    art_dir = _artifacts_dir()
    safe = Path(name).name  # 防路径穿越：只取 basename
    target = art_dir / safe
    if not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"read failed: {e}") from e
    return {"name": safe, "path": str(target), "content": content,
            "size": target.stat().st_size}


@router.get("/documents/tools")
async def document_tools() -> dict:
    """MCP-Doc（腾讯 Word 处理服务）工具清单（右侧栏展示用）。"""
    tools = [
        {"name": "create_document", "desc": "创建新 Word 文档"},
        {"name": "open_document", "desc": "打开已有文档"},
        {"name": "save_document", "desc": "保存文档"},
        {"name": "add_paragraph", "desc": "添加段落"},
        {"name": "add_heading", "desc": "添加标题"},
        {"name": "add_table", "desc": "添加表格"},
        {"name": "get_document_info", "desc": "文档信息"},
        {"name": "search_and_replace", "desc": "查找替换"},
        {"name": "replace_section", "desc": "按关键词替换章节（保留格式）"},
        {"name": "edit_section_by_keyword", "desc": "按关键词编辑章节"},
        {"name": "set_page_margins", "desc": "页边距"},
        {"name": "add_page_break", "desc": "分页符"},
        {"name": "merge_table_cells", "desc": "合并表格单元格"},
        {"name": "delete_text", "desc": "删除文本"},
    ]
    return {"count": len(tools), "tools": tools}
