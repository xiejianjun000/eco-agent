"""
EcoAegis AuthService — hermes 插件适配器。

由 hermes 后端统一调度，注册以下工具：
  - auth_health  : 轻量会话探针，复用 storageState 检测平台登录态
  - auth_login   : 触发自动登录（调用 auto_login.js）
  - auth_captcha  : 列出待人工识别的验证码样本
"""

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# ── 项目根目录（hermes-agent/ 的父级，即 EcoAegis/） ──
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent  # hermes-plugins/ecoaegis/ → EcoAegis/
_AUTH_DIR = _PROJECT_ROOT / "auth"
_STATE_DIR = _AUTH_DIR / "state"

# ── 平台配置 ──
PLATFORMS = {
    "atmosphere": {
        "label": "大气监督帮扶",
        "url_env": "ECOAEGIS_PLATFORM_URL_ATMOSPHERE",
        "default_url": "http://114.251.10.199:8080/zfpt_zf/redirect.jsp",
    },
    "water": {
        "label": "水环境管理",
        "url_env": "ECOAEGIS_PLATFORM_URL_WATER",
        "default_url": "http://114.251.10.199:8080/zfpt_water/redirect.jsp",
    },
}

# ── 会话探针参数 ──
SESSION_MAX_IDLE_DAYS = 7


# ═══════════════════════════════════════════════════════════════════
# 工具实现
# ═══════════════════════════════════════════════════════════════════

def _read_heartbeat_ledger(platform_id: str) -> Dict[str, Any]:
    """读取心跳账本文件。"""
    ledger_path = _STATE_DIR / f"{platform_id}.json"
    if not ledger_path.exists():
        return {"status": "never_authed", "platform": platform_id}
    try:
        return json.loads(ledger_path.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "ledger_corrupt", "platform": platform_id}


def _write_heartbeat_ledger(platform_id: str, data: Dict[str, Any]) -> None:
    """写入心跳账本文件。"""
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    ledger_path = _STATE_DIR / f"{platform_id}.json"
    ledger_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def auth_health(platform: str = "", task_id: str = None) -> str:
    """
    检测平台登录态是否有效。

    三信号判定：
      1. storageState 文件是否存在
      2. 账本记录的认证时间是否在有效期内
      3. 最近的探针结果

    返回 JSON 格式的状态报告。
    """
    results = []
    platforms_to_check = (
        [p for p in PLATFORMS if p.startswith(platform)]
        if platform else list(PLATFORMS)
    )
    if not platforms_to_check:
        return json.dumps(
            {"error": f"未知平台: {platform}", "available": list(PLATFORMS)},
            ensure_ascii=False,
        )

    now = datetime.now(timezone.utc)

    for pid in platforms_to_check:
        cfg = PLATFORMS[pid]
        state_file = _STATE_DIR / f"{pid}.storageState.json"
        ledger = _read_heartbeat_ledger(pid)

        # 信号 1：storageState 是否存在
        has_state = state_file.exists()
        state_size = state_file.stat().st_size if has_state else 0

        # 信号 2：账本认证时间
        last_auth_at = ledger.get("lastCredentialAuthAt") or ledger.get("lastSessionOkAt")
        auth_age_days = None
        if last_auth_at:
            try:
                last_auth_dt = datetime.fromisoformat(last_auth_at)
                auth_age_days = (now - last_auth_dt).total_seconds() / 86400
            except (ValueError, TypeError):
                pass

        # 信号 3：探针结果
        probe_ok = ledger.get("status") == "ok"
        auth_mode = ledger.get("authMode", "unknown")

        # 综合判定
        if not has_state:
            status = "NO_STATE"
            detail = "storageState 文件不存在，从未成功登录或已被清理"
            severity = "critical"
        elif auth_age_days is None:
            status = "UNKNOWN_AGE"
            detail = "storageState 存在但无法确定认证时间"
            severity = "warning"
        elif auth_age_days > SESSION_MAX_IDLE_DAYS * 2:
            status = "EXPIRED"
            detail = f"上次凭据认证距今 {auth_age_days:.0f} 天，远超 {SESSION_MAX_IDLE_DAYS} 天阈值，需要重新登录"
            severity = "critical"
        elif auth_age_days > SESSION_MAX_IDLE_DAYS:
            status = "STALE"
            detail = f"上次凭据认证距今 {auth_age_days:.0f} 天，超过 {SESSION_MAX_IDLE_DAYS} 天阈值"
            severity = "warning"
        elif not probe_ok:
            status = "PROBE_FAILED"
            detail = "探针检测失败，会话可能已过期"
            severity = "warning"
        else:
            status = "HEALTHY"
            detail = f"会话有效（上次认证: {auth_age_days:.1f} 天前）"
            severity = "ok"

        results.append({
            "platform": pid,
            "label": cfg["label"],
            "status": status,
            "severity": severity,
            "hasState": has_state,
            "stateSize": state_size,
            "authAgeDays": round(auth_age_days, 1) if auth_age_days else None,
            "authMode": auth_mode,
            "lastAuthAt": last_auth_at,
            "detail": detail,
        })

    return json.dumps({"checkedAt": now.isoformat(), "platforms": results}, ensure_ascii=False)


def auth_login(platform: str = "atmosphere", task_id: str = None) -> str:
    """
    触发指定平台的自动登录。

    调用 auto_login.js 执行完整的登录流程（浏览器启动 → 凭据填充 → 验证码识别 → 提交）。
    成功时导出 storageState 到 auth/state/。
    """
    if platform not in PLATFORMS:
        return json.dumps(
            {"error": f"未知平台: {platform}", "available": list(PLATFORMS)},
            ensure_ascii=False,
        )

    cfg = PLATFORMS[platform]
    auto_login_script = _PROJECT_ROOT / "auto_login.js"

    if not auto_login_script.exists():
        return json.dumps(
            {"error": f"登录脚本不存在: {auto_login_script}", "platform": platform},
            ensure_ascii=False,
        )

    # 构建环境变量
    env = os.environ.copy()
    platform_url = os.environ.get(cfg["url_env"], cfg["default_url"])
    env["PLATFORM_URL"] = platform_url
    env["ECOAEGIS_PLATFORM"] = platform  # 让 auto_login.js 知道用哪个平台的 Keychain 凭据

    try:
        start = time.time()
        result = subprocess.run(
            ["node", str(auto_login_script)],
            cwd=str(_PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=240,  # 4 分钟超时
        )
        elapsed = round(time.time() - start, 1)

        output = {
            "platform": platform,
            "label": cfg["label"],
            "exitCode": result.returncode,
            "elapsedSeconds": elapsed,
            "stdout": result.stdout[-3000:],  # 截断，避免过长
        }

        if result.returncode == 0:
            # 验证 storageState 是否已写入
            state_file = _STATE_DIR / f"{platform}.storageState.json"
            output["success"] = True
            output["stateSaved"] = state_file.exists()
            # 写入心跳账本（修复死函数：之前从不写账本，导致 auth_health 永远不报告 HEALTHY）
            now_iso = datetime.now(timezone.utc).isoformat()
            _write_heartbeat_ledger(platform, {
                "status": "ok",
                "lastCredentialAuthAt": now_iso,
                "lastSessionOkAt": now_iso,
                "authMode": "plugin",
            })
            ledger = _read_heartbeat_ledger(platform)
            output["ledgerStatus"] = ledger.get("status", "unknown")
        else:
            output["success"] = False
            output["stderr"] = result.stderr[-2000:]

        return json.dumps(output, ensure_ascii=False)

    except subprocess.TimeoutExpired:
        return json.dumps(
            {"platform": platform, "success": False, "error": "登录超时（4 分钟）"},
            ensure_ascii=False,
        )
    except FileNotFoundError:
        return json.dumps(
            {"platform": platform, "success": False, "error": "Node.js 未安装或路径不正确"},
            ensure_ascii=False,
        )


def auth_captcha(platform: str = "atmosphere", task_id: str = None) -> str:
    """
    列出最近保存的验证码样本，供人工或视觉模型识别。
    """
    captcha_dir = _AUTH_DIR / "captcha_samples"
    if not captcha_dir.exists():
        return json.dumps(
            {"platform": platform, "samples": [], "hint": "尚无验证码样本，请先运行 auth_login"},
            ensure_ascii=False,
        )

    samples = sorted(
        captcha_dir.glob("captcha_*.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:10]

    return json.dumps(
        {
            "platform": platform,
            "count": len(samples),
            "samples": [
                {
                    "name": s.name,
                    "path": str(s),
                    "size": s.stat().st_size,
                    "createdAt": datetime.fromtimestamp(s.stat().st_mtime, tz=timezone.utc).isoformat(),
                }
                for s in samples
            ],
        },
        ensure_ascii=False,
    )


def auth_setup_cron(task_id: str = None) -> str:
    """
    一键初始化 EcoAegis cron 作业（心跳 + 巡更）。
    返回需要执行的 hermes cron create 命令列表。
    """
    commands = [
        # 每日心跳：07:50 / 14:00 / 19:00
        {
            "description": "早间心跳检测",
            "command": 'hermes cron create "50 7 * * *" "运行 auth_health 检测所有平台登录态。如有 critical 告警请投递到通知频道。" --name ecoaegis-heartbeat-morning --deliver ecoaegis',
        },
        {
            "description": "午间心跳检测",
            "command": 'hermes cron create "0 14 * * *" "运行 auth_health 检测所有平台登录态。如有 critical 告警请投递到通知频道。" --name ecoaegis-heartbeat-noon --deliver ecoaegis',
        },
        {
            "description": "晚间心跳检测",
            "command": 'hermes cron create "0 19 * * *" "运行 auth_health 检测所有平台登录态。如有 critical 告警请投递到通知频道。" --name ecoaegis-heartbeat-evening --deliver ecoaegis',
        },
        # 每周凭据验证
        {
            "description": "每周凭据验证（大气平台）",
            "command": 'hermes cron create "0 8 * * 1" "运行 auth_login atmosphere 进行完整凭据验证登录。" --name ecoaegis-login-atmosphere --deliver ecoaegis',
        },
    ]

    return json.dumps(
        {
            "message": "请在 hermes CLI 中执行以下命令来设置 cron 作业",
            "commands": commands,
            "note": "auth_health 和 auth_login 工具通过 ecoaegis 插件提供，确保插件已启用。",
        },
        ensure_ascii=False,
    )


# ═══════════════════════════════════════════════════════════════════
# 插件注册
# ═══════════════════════════════════════════════════════════════════

def register(ctx) -> None:
    """EcoAegis 插件入口 — 由 hermes 插件系统调用。"""

    # ── auth_health ──
    ctx.register_tool(
        name="auth_health",
        toolset="ecoaegis",
        schema={
            "name": "auth_health",
            "description": "检测环保政务平台的登录会话状态。检查 storageState 文件、认证时间、探针结果三信号，返回各平台的健康状态报告（HEALTHY / STALE / EXPIRED / NO_STATE）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "平台 ID（atmosphere / water），留空检测全部平台",
                    },
                },
                "required": [],
            },
        },
        handler=lambda args, **kw: auth_health(
            platform=args.get("platform", ""),
            task_id=kw.get("task_id"),
        ),
        emoji="💓",
    )

    # ── auth_login ──
    ctx.register_tool(
        name="auth_login",
        toolset="ecoaegis",
        schema={
            "name": "auth_login",
            "description": "对指定环保政务平台执行完整自动登录（浏览器启动 → 凭据填充 → 验证码 OCR → 提交）。成功时导出 Playwright storageState 并更新心跳账本。慎用：登录失败多次可能锁定账号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "平台 ID，默认 atmosphere（大气监督帮扶）。注意：水环境平台(CAS登录)请使用独立的 patrol_login.py",
                        "enum": ["atmosphere"],
                    },
                },
                "required": ["platform"],
            },
        },
        handler=lambda args, **kw: auth_login(
            platform=args.get("platform", "atmosphere"),
            task_id=kw.get("task_id"),
        ),
        emoji="🔐",
    )

    # ── auth_captcha ──
    ctx.register_tool(
        name="auth_captcha",
        toolset="ecoaegis",
        schema={
            "name": "auth_captcha",
            "description": "列出最近保存的验证码图片样本，供人工识别或视觉 AI 辅助解码。验证码 OCR（ddddocr）准确率约 40%，识别失败时可用此工具查看样本。",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {
                        "type": "string",
                        "description": "平台 ID，默认 atmosphere",
                    },
                },
                "required": [],
            },
        },
        handler=lambda args, **kw: auth_captcha(
            platform=args.get("platform", "atmosphere"),
            task_id=kw.get("task_id"),
        ),
        emoji="🔍",
    )

    # ── auth_setup_cron ──
    ctx.register_tool(
        name="auth_setup_cron",
        toolset="ecoaegis",
        schema={
            "name": "auth_setup_cron",
            "description": "生成 EcoAegis 心跳与巡更的 cron 作业创建命令。一键配置每日三次心跳检测 + 每周凭据验证。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        handler=lambda args, **kw: auth_setup_cron(task_id=kw.get("task_id")),
        emoji="⏰",
    )

    logger.info("EcoAegis 插件已注册: auth_health, auth_login, auth_captcha, auth_setup_cron")
