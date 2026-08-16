#!/usr/bin/env python3
"""
eco server - Management API + Web GUI 服务

端面：见 server/app.py 模块文档。
用法：
  eco server                 # 默认 127.0.0.1:8788
  eco server --port 9000 --host 0.0.0.0
  eco server --reload        # 开发模式
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("eco.server")

ROOT = Path(__file__).resolve().parent.parent.parent


def run(args):
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        import uvicorn  # noqa: F401
        import fastapi  # noqa: F401
    except ImportError:
        log.error("Missing dependencies. Run: pip install fastapi uvicorn")
        return 1

    from server.app import create_app, get_version

    app = create_app()
    log.info("\n  ECO AGENT Management API (v%s)", get_version())
    log.info("  API docs: http://%s:%s/docs", args.host, args.port)
    log.info("  Health:   http://%s:%s/healthz", args.host, args.port)
    log.info("  Chat:     POST http://%s:%s/api/v1/chat\n", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0
