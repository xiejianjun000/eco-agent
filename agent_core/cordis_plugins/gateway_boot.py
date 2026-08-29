#!/usr/bin/env python3
"""
agent_core/cordis_plugins/gateway_boot.py — 多平台网关自动启动插件
====================================================================
对标 DSH「一切皆插件」：把独立网关（gateway/eco-gateway-server.py，飞书/
企业微信/钉钉 webhook）随主服务一起拉起来——凭证填好即一条命令跑通，
不必再单独 `python gateway/eco-gateway-server.py`。

行为：
  - 按已配置凭证自动选择平台（FEISHU_APP_ID→feishu，WECOM_CORP_ID→wecom）
  - 无凭证则跳过（网关仍可手动启动），不阻塞主服务
  - 子进程托管：卸载时 terminate 回收

配置（eco.cordis.yml）：
  - plugin: agent_core.cordis_plugins.gateway_boot
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("eco.cordis.gateway_boot")

_ROOT = Path(__file__).resolve().parent.parent.parent
_GATEWAY = _ROOT / "gateway" / "eco-gateway-server.py"

_PLATFORM_ENV = {
    "feishu": "FEISHU_APP_ID",
    "wecom": "WECOM_CORP_ID",
    "dingtalk": "DINGTALK_APP_KEY",
}


def apply(ctx, config: dict | None = None) -> None:
    """组合装配入口：按凭证自动拉起网关子进程（幂等）。"""
    platforms = [p for p, env in _PLATFORM_ENV.items() if os.environ.get(env)]
    if not platforms:
        logger.info("[gateway_boot] 无平台凭证（FEISHU_APP_ID/WECOM_CORP_ID/...），"
                    "跳过网关自动启动——可手动 python gateway/eco-gateway-server.py")
        ctx.provide("gateway", {"running": False, "platforms": []})
        return
    if not _GATEWAY.is_file():
        logger.warning("[gateway_boot] 网关入口缺失: %s", _GATEWAY)
        return
    cmd = [sys.executable, str(_GATEWAY), "--platforms", ",".join(platforms)]
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(_ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError as e:  # noqa: BLE001
        logger.warning("[gateway_boot] 网关启动失败: %s", e)
        return
    ctx.provide("gateway", {"running": True, "platforms": platforms, "pid": proc.pid})
    ctx.effect(lambda: proc.terminate(), label="gateway_boot.stop")
    logger.info("[gateway_boot] 网关已拉起: platforms=%s pid=%s", platforms, proc.pid)
