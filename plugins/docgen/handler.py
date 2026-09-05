#!/usr/bin/env python3
"""
plugins/docgen/handler.py — 文档生成插件

能力: generate_pptx（PPT 文件真实产出，纯标准库 OOXML）
输出目录: eco-agent/output/（可注入 DOCGEN_OUTPUT_DIR 覆盖）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUTPUT = ROOT / "output"


def _gen_pptx(slides: list, title: str = "未命名", filename: str = "") -> str:
    """生成 PPTX 并返回真实文件路径。slides: [{title, bullets}]。"""
    import os

    out_dir = Path(os.environ.get("DOCGEN_OUTPUT_DIR", str(DEFAULT_OUTPUT)))
    out_dir.mkdir(parents=True, exist_ok=True)
    if not isinstance(slides, list) or not slides:
        return json.dumps({"error": "slides 必须是非空列表"}, ensure_ascii=False)

    sys.path.insert(0, str(ROOT))
    from scripts.gen_pptx import build_pptx

    try:
        data = build_pptx(slides)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"error": f"生成失败: {e}"}, ensure_ascii=False)
    safe_name = (filename or title).replace("/", "_").replace(" ", "_")[:40]
    path = out_dir / f"{safe_name}.pptx"
    path.write_bytes(data)
    return json.dumps({"ok": True, "path": str(path), "bytes": len(data), "slides": len(slides)}, ensure_ascii=False)


def load(ctx):
    ctx.register_tool(
        "generate_pptx",
        _gen_pptx,
        description="生成 PowerPoint 演示文稿（.pptx 真实文件）——输入每页标题与要点",
        risk_level="L2",
    )

    # 注册进 LLM 可见工具表
    from agent_core.tools_registry import register_external_tool

    register_external_tool(
        name="generate_pptx",
        description="生成 PowerPoint 演示文稿文件（多页标题+要点），返回真实文件路径",
        parameters={
            "type": "object",
            "properties": {
                "slides": {
                    "type": "array",
                    "description": "每页: {title: 页标题, bullets: [要点]}",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "bullets": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["title"],
                    },
                },
                "title": {"type": "string", "description": "演示文稿名称（用于文件名）"},
                "filename": {"type": "string", "description": "可选文件名"},
            },
            "required": ["slides"],
        },
        handler=_gen_pptx,
        risk_level="L2",
        source="docgen",
    )
    ctx.log("docgen plugin loaded: generate_pptx")
    return {"ok": True, "tools": sorted(ctx.tools.keys())}


def unload(ctx):
    from agent_core.tools_registry import unregister_external_tool

    unregister_external_tool("generate_pptx")
    ctx.log("docgen plugin unloaded")
    return {"ok": True}
