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

    # 启动前置诊断：模型密钥为空时给出明确告警（envboot 已做空值遮蔽补填）
    import os

    # L4 审批栈默认批准人：单机部署下能调本机 /decide 接口的人即管理员
    os.environ.setdefault("ECO_APPROVAL_ANSWERERS", "admin")

    if not (os.environ.get("DEEPSEEK_API_KEY", "") or "").strip():
        log.error("⚠️  DEEPSEEK_API_KEY 为空：LLM 将报 no api key。"
                  "请检查仓库 .env / ~/.eco/.env，或运行 python3 _scripts/setup_credentials.py")

    app = create_app()
    log.info("\n  eco Agent Management API (v%s)", get_version())
    log.info("  Web GUI:  http://%s:%s/", args.host, args.port)
    log.info("  API docs: http://%s:%s/docs", args.host, args.port)
    log.info("  Health:   http://%s:%s/healthz", args.host, args.port)
    log.info("  Chat:     POST http://%s:%s/api/v1/chat\n", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0
