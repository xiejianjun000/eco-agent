#!/usr/bin/env python3
"""
agent_core/cordis_plugins/builtin_tools.py — 内置能力工具集插件
====================================================================
对标 DSH「工具即插件」：statute_lookup/statute_search（法典检索）与
tdocs_upload_html（腾讯文档上云）从 chat.py 硬编码走向组合装配。

说明：聊天通道 _run_tool 的 statute_/tdocs 分支保留（行为不变），
本插件把同名 handler 注册进 tools_registry——让 subagent、外部调用方、
eco doctor 等"工具即服务"消费方也能按注册表反查执行，且新增/下线
工具只改本文件与 eco.cordis.yml。
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("eco.cordis.builtin_tools")

_ROOT = Path(__file__).resolve().parent.parent.parent
_LOOKUP = _ROOT / "ecoskills" / "eco-codex" / "scripts" / "lookup.py"


def _statute_handler(article: str = "", keyword: str = "",
                     mode: str = "article") -> str:
    """法典条文直查/关键词检索（子进程调 lookup.py，与 chat 通道同源）。"""
    if mode == "search":
        cmd = [sys.executable, str(_LOOKUP), "search", keyword]
    else:
        cmd = [sys.executable, str(_LOOKUP), "article", article]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or r.stderr.strip()[:300]
    except Exception as e:  # noqa: BLE001
        return f"法典检索失败: {e}"


def _tdocs_handler(path: str = "", title: str = "") -> str:
    """腾讯文档 HTML 一键上云（aipage 打包 + 导入管线）。"""
    try:
        from agent_core.tdocs_import import tdocs_upload_html

        result = tdocs_upload_html(path or "", title or "")
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:  # noqa: BLE001
        return json.dumps({"ok": False, "error": f"上传失败: {e}"},
                          ensure_ascii=False)


def apply(ctx, config: dict | None = None) -> None:
    """组合装配入口：注册内置能力工具 handler（幂等）。"""
    from agent_core.tools_registry import register_external_tool

    entries = [
        ("statute_lookup",
         "生态环境法典条文精确检索——按条号（如1054或第一千零五十四条）返回条文原文",
         {"type": "object",
          "properties": {"article": {"type": "string",
                                     "description": "条号（如1054）"}},
          "required": ["article"]},
         lambda **kw: _statute_handler(article=str(kw.get("article", "")),
                                       mode="article")),
        ("statute_search",
         "生态环境法典关键词检索——按关键词返回相关条文",
         {"type": "object",
          "properties": {"keyword": {"type": "string"}},
          "required": ["keyword"]},
         lambda **kw: _statute_handler(keyword=str(kw.get("keyword", "")),
                                       mode="search")),
        ("tdocs_upload_html",
         "数据分析 HTML 报告一键上传为腾讯文档在线文档（aipage 打包+导入）",
         {"type": "object",
          "properties": {"path": {"type": "string"},
                         "title": {"type": "string"}},
          "required": ["path"]},
         lambda **kw: _tdocs_handler(path=str(kw.get("path", "")),
                                     title=str(kw.get("title", "")))),
    ]
    registered: list[str] = []
    from agent_core.tools_registry import _HANDLERS as _EXISTING
    for name, desc, params, handler in entries:
        if name in _EXISTING:
            continue  # 已注册：幂等跳过
        try:
            register_external_tool(name, desc, params, handler,
                                   level="L1", category="内置能力")
            registered.append(name)
        except Exception as e:  # noqa: BLE001 — 幂等注册
            logger.debug("[builtin_tools] %s 注册跳过: %s", name, e)
    logger.info("[builtin_tools] 组合装配注册 %d 个内置工具: %s",
                len(registered), registered)
