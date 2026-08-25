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

from fastapi import Request, FastAPI

logger = logging.getLogger("eco.server")


def get_version() -> str:
    from eco import __version__

    return __version__


def create_app() -> FastAPI:
    # 进程级环境引导：仓库 .env + ~/.eco/.env 合入 os.environ（MCP 连接器等依赖）
    from agent_core.envboot import load_env_into_process

    load_env_into_process()

    app = FastAPI(
        title="ECO AGENT API",
        description="ECO AGENT 管理 API — 面向应用与 Web GUI 的 REST/SSE 接口",
        version=get_version(),
    )

    # cordis 组合内核装配（服务注册 + 组合插件装载，对标 DSH boot）
    try:
        from agent_core.cordis.boot import get_app_context

        get_app_context()
    except Exception:  # noqa: BLE001 — 装配失败不阻断 API
        pass

    from server.api import approvals, chat, documents, dynamic_plugins, files, goals, inspect, memory, plugins, prompt, sessions, skills, slots, subagents, system, tools, workflow

    app.include_router(documents.router, prefix="/api/v1", tags=["documents"])
    app.include_router(files.router, prefix="/api/v1", tags=["files"])
    app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
    app.include_router(sessions.router, prefix="/api/v1", tags=["sessions"])
    app.include_router(memory.router, prefix="/api/v1", tags=["memory"])
    app.include_router(skills.router, prefix="/api/v1", tags=["skills"])
    app.include_router(tools.router, prefix="/api/v1", tags=["tools"])
    app.include_router(plugins.router, prefix="/api/v1", tags=["plugins"])
    app.include_router(prompt.router, prefix="/api/v1", tags=["prompt"])
    app.include_router(subagents.router, prefix="/api/v1/subagents", tags=["subagents"])
    app.include_router(goals.router, prefix="/api/v1", tags=["goals"])
    app.include_router(inspect.router, prefix="/api/v1", tags=["inspect"])
    app.include_router(workflow.router, prefix="/api/v1", tags=["workflow"])
    app.include_router(dynamic_plugins.router, prefix="/api/v1", tags=["dynamic-plugins"])
    app.include_router(slots.router, prefix="/api/v1", tags=["slots"])
    app.include_router(approvals.router, prefix="/api/v1", tags=["approvals"])
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
    from fastapi.staticfiles import StaticFiles

    # 整个 dist 作为静态根（含 public/ 拷贝产物：favicon.svg、eco-logo.svg 等）。
    # 注册在所有 API 路由之后：/api/v1、/healthz 等由路由优先处理，其余路径回退 SPA 静态文件。
    # index.html 禁缓存（改版后刷新即取新 bundle）；哈希资产文件名自带版本，可长缓存
    from fastapi.responses import FileResponse
    from starlette.responses import Response

    async def _no_cache_index(request: Request):
        return FileResponse(web_dist / "index.html", headers={
            "Cache-Control": "no-store"})

    app.mount("/assets", StaticFiles(directory=str(web_dist / "assets")), name="web-assets")
    app.add_api_route("/", _no_cache_index, methods=["GET"])
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="web-gui")


def run(host: str = "127.0.0.1", port: int = 8788, reload: bool = False) -> None:
    """uvicorn 入口（供 CLI / 脚本调用）。"""
    import uvicorn

    uvicorn.run("server.app:create_app", factory=True, host=host, port=port, reload=reload)
