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
from fastapi.responses import FileResponse

logger = logging.getLogger("eco.server.documents")

router = APIRouter()

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"

# 前端本地渲染器（docx-preview / pdf.js / xlsx）依赖正确的 MIME 判定
_MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".md": "text/markdown",
    ".html": "text/html",
    ".json": "application/json",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".svg": "image/svg+xml",
}


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
                files.append(
                    {
                        "name": f.name,
                        "path": str(f),
                        "size_kb": round(st.st_size / 1024, 1),
                        "modified": st.st_mtime,
                    }
                )
    # 回答产物（MD）并入文档列表：持久落盘，重启仍在
    art_dir = _artifacts_dir()
    artifacts = []
    if art_dir.is_dir():
        for f in sorted(art_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            st = f.stat()
            artifacts.append(
                {
                    "name": f.name,
                    "path": str(f),
                    "size_kb": round(st.st_size / 1024, 1),
                    "modified": st.st_mtime,
                    "kind": "artifact",
                }
            )
    return {"count": len(files) + len(artifacts), "files": files, "artifacts": artifacts}


def _presentable_roots() -> list[Path]:
    """present_files 允许下载的目录白名单。

    严格限定，绝不接受任意路径 —— 端点入参是模型给的，
    没有白名单就是任意文件读取漏洞。
    """
    roots = [_artifacts_dir(), OUTPUT_DIR]
    repo = Path(__file__).resolve().parent.parent.parent
    roots.append(repo / "deliverables")
    ws = os.environ.get("ECO_WORKSPACE")
    if ws:
        roots.append(Path(ws) / "deliverables")
    return [r for r in roots if r.is_dir()]


@router.get("/presented")
async def download_presented(path: str) -> FileResponse:
    """下载 present_files 呈现的成果文件（对标 WorkBuddy artifact card）。

    只允许白名单目录内的真实文件；软链接一律按解析后的真实路径再校验一次。
    """
    try:
        target = Path(path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise HTTPException(status_code=404, detail="file not found") from e
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not a file")
    roots = _presentable_roots()
    if not any(target.is_relative_to(r.resolve()) for r in roots):
        raise HTTPException(status_code=403, detail="path outside allowed roots")
    return FileResponse(path=str(target), filename=target.name,
                        media_type="application/octet-stream")


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
    return {"name": safe, "path": str(target), "content": content, "size": target.stat().st_size}


@router.get("/documents/artifact/{name}/download")
async def download_artifact(name: str) -> FileResponse:
    """下载回答产物文件（Content-Disposition attachment，浏览器触发下载）。"""
    art_dir = _artifacts_dir()
    target = art_dir / Path(name).name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if target.suffix.lower() == ".docx"
        else "text/markdown"
    )
    return FileResponse(str(target), filename=target.name, media_type=media_type)


@router.get("/documents/file")
async def read_file_binary(name: str) -> FileResponse:
    """按文件名返回 output/ 或 artifacts/ 内的原始二进制（前端 docx/pdf/xlsx 渲染用）。

    仅接受 basename（Path(name).name 剥掉任何目录成分），再在两个白名单目录内
    查找并用 resolve() 复核父目录，双重防路径穿越；不接受任意路径参数。
    """
    safe = Path(name).name
    if not safe or safe.startswith("."):
        raise HTTPException(status_code=400, detail="invalid name")

    for base in (OUTPUT_DIR, _artifacts_dir()):
        target = base / safe
        if not target.is_file():
            continue
        try:
            resolved = target.resolve()
            if resolved.parent != base.resolve():
                continue
        except OSError:
            continue
        return FileResponse(
            str(resolved),
            filename=resolved.name,
            media_type=_MEDIA_TYPES.get(resolved.suffix.lower(), "application/octet-stream"),
        )
    raise HTTPException(status_code=404, detail="file not found")


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
