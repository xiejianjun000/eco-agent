#!/usr/bin/env python3
"""
server/app.py — ECO AGENT 管理 API 应用工厂

端面一览：
  POST   /api/v1/chat              对话（非流式，含 system prompt 构建）
  POST   /api/v1/chat/stream       对话（SSE 流式）
  GET    /api/v1/sessions          会话列表（复用 gateway SessionManager, platform=web）
  POST   /api/v1/sessions          创建/续用会话
  GET    /api/v1/memory/nodes      记忆树节点列表
  GET    /api/v1/memory/search     记忆树检索（关键词/混合）
  GET    /api/v1/memory/stats      记忆统计
  GET    /api/v1/skills            技能列表
  GET    /api/v1/skills/search     技能检索
  GET    /api/v1/tools             工具目录（govmcp 工具注册表）
  GET    /api/v1/system            系统健康与统计
  GET    /api/v1/metrics           token/成本指标
  GET    /api/v1/version           版本信息
  GET    /healthz                  健康检查

所有业务能力均复用 agent_core / gateway / govmcp 现有接口，本层不做 AI 逻辑。
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# 保证 repo 根在 sys.path（_scripts、agent_core 等包可直接导入）
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI

logger = logging.getLogger("eco.server")


def get_version() -> str:
    from eco import __version__

    return __version__


def create_app() -> FastAPI:
    app = FastAPI(
        title="ECO AGENT API",
        description="ECO AGENT 管理 API — 面向应用与 Web GUI 的 REST/SSE 接口",
        version=get_version(),
    )

    from server.api import chat, memory, plugins, sessions, skills, system, tools

    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
    app.include_router(memory.router, prefix="/api/v1", tags=["memory"])
    app.include_router(skills.router, prefix="/api/v1", tags=["skills"])
    app.include_router(tools.router, prefix="/api/v1", tags=["tools"])
    app.include_router(plugins.router, prefix="/api/v1", tags=["plugins"])
    app.include_router(system.router, prefix="/api/v1", tags=["system"])

    @app.get("/healthz", tags=["system"])
    async def healthz() -> dict:
        return {"status": "ok", "version": get_version()}

    _mount_web_gui(app)
    return app


def _mount_web_gui(app: FastAPI) -> None:
    """挂载 web/dist 静态前端（SPA）。未构建时静默跳过，API 仍可用。"""
    web_dist = _ROOT / "web" / "dist"
    if not web_dist.is_dir():
        logger.info("web/dist not found — Web GUI 未构建（cd web && npm run build），仅 API 可用")
        return
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=str(web_dist / "assets")), name="web-assets")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(str(web_dist / "index.html"))


def run(host: str = "127.0.0.1", port: int = 8788, reload: bool = False) -> None:
    """uvicorn 入口（供 CLI / 脚本调用）。"""
    import uvicorn

    uvicorn.run("server.app:create_app", factory=True, host=host, port=port, reload=reload)
