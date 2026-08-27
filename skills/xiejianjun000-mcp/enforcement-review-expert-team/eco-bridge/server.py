"""
eco-bridge — EcoAegis 前端 ↔ Hermes agent 基座 的薄桥接（HTTP 门面）
====================================================================

v2 更新：
  - 实现 call_hermes() 核心桥接函数（占位 + 真实双模）
  - 新增 /api/office/* 协同编辑端点（文档打开 / AI 审阅 / 状态查询）
  - 已有 /api/platform/* 端点改用 call_hermes() 驱动
  - 新增 /api/auth/health 端点（对接 Hermes ecoaegis 插件）

运行:
  python server.py          # 默认 :8787（仅 Python 标准库）
  HERMES_REAL=1 python server.py  # 启用真实 Hermes 引擎
"""

from __future__ import annotations

import json
import os
import re
import secrets
import ssl as _ssl
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import urlopen, Request as UrlRequest
from urllib.error import URLError, HTTPError
import queue

# 执法办案 Skill（可选依赖，按需加载）
_enforcement_skill = None


def _get_enforcement_skill():
    """延迟加载执法办案 Skill 模块"""
    global _enforcement_skill
    if _enforcement_skill is None:
        try:
            from skills.enforcement_platform import EnforcementPlatform, create_platform, quick_sync, quick_inspect
            _enforcement_skill = {
                "EnforcementPlatform": EnforcementPlatform,
                "create_platform": create_platform,
                "quick_sync": quick_sync,
                "quick_inspect": quick_inspect,
            }
        except ImportError as e:
            _enforcement_skill = {"error": str(e)}
    return _enforcement_skill

PORT = int(os.getenv("ECO_BRIDGE_PORT", "8787"))
BIND_ADDR = os.getenv("ECO_BRIDGE_BIND", "127.0.0.1")  # CVE-01: 默认仅本地, 需局域网时设 0.0.0.0
CORS_ORIGIN = os.getenv("ECO_BRIDGE_CORS", "http://localhost:5173")  # CVE-01: 精确CORS, 非 *
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
AUTH_DIR = os.path.join(PROJECT_ROOT, "auth")
STATE_DIR = os.path.join(AUTH_DIR, "state")
# N2: 白名单输出目录——enforcement 端点只允许写入这些路径
SAFE_OUTPUT_DIRS = [
    os.path.join(HERE, "data"),
    os.path.join(PROJECT_ROOT, "output"),
    os.path.join(PROJECT_ROOT, "eco-enforcement-assistant"),
    "/tmp/eco-aegis-sync",
    "/tmp/eco-aegis-docs",
    "/tmp/eco-aegis-export",
]

def _sanitize_output_path(user_path: str) -> str:
    """校验并清洗用户提供的输出路径, 防止路径遍历 (CVE-02 残留 / N2)。"""
    import os
    resolved = os.path.realpath(os.path.join(PROJECT_ROOT, user_path) if not os.path.isabs(user_path) else user_path)
    allowed = any(resolved.startswith(os.path.realpath(d)) for d in SAFE_OUTPUT_DIRS)
    if not allowed:
        raise ValueError(f"输出路径不在白名单内: {resolved}")
    return resolved


def _sse_send(q: queue.Queue, event: str, data: dict) -> None:
    """向 SSE 队列发送事件。"""
    q.put({"event": event, "data": data})

with open(os.path.join(HERE, "data", "platforms.json"), encoding="utf-8") as _f:
    PLATFORMS: list[dict] = json.load(_f)


def _save_platforms() -> None:
    """将内存中的 PLATFORMS 写回 platforms.json。"""
    fp = os.path.join(HERE, "data", "platforms.json")
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(PLATFORMS, f, ensure_ascii=False, indent=2)


def _normalize_match_result(raw: dict) -> dict:
    """将 Hermes 返回的 match_platform 结果归一化为前端期望的 {matched, platform?, reason?} 格式。

    真实 Hermes 返回格式多变，本函数处理所有已知变体：
    - 占位模式: {matched: bool, platform?: dict, reason?: str}
    - 变体A: {action, platform: str, status: "MATCHED"/"NOT_MATCHED", platformId, ...}
    - 变体B: {matched: true, platform: "平台名称", platformCode: "xxx", ...}
    - platform 可能是 dict 或 str

    策略：先查本地白名单，找不到就自动加入。
    """
    matched = raw.get("matched")
    status = (raw.get("status") or "").upper()

    # 判断是否匹配
    is_match = matched is True or status == "MATCHED"
    if not is_match:
        reason = raw.get("reason") or raw.get("message", "不在白名单内")
        return {"matched": False, "reason": reason}

    # ── 提取平台关键信息 ──
    platform_raw = raw.get("platform")
    pid = (raw.get("platformId") or raw.get("platformCode") or "").strip()
    name = ""
    if isinstance(platform_raw, dict):
        name = platform_raw.get("name", "") or pid
        # 如果已经是完整 platform 对象，直接返回
        if "id" in platform_raw and "keywords" in platform_raw:
            return {"matched": True, "platform": platform_raw}
        if platform_raw.get("id"):
            pid = platform_raw["id"]
    elif isinstance(platform_raw, str) and platform_raw.strip():
        name = platform_raw.strip()
    if not name:
        name = raw.get("name") or raw.get("message") or pid or "未知平台"

    # 在本地白名单中查找
    for p in PLATFORMS:
        if pid and p["id"] == pid:
            return {"matched": True, "platform": p}
        if name and name.lower() in (p.get("name", "") or "").lower():
            return {"matched": True, "platform": p}

    # 本地白名单没有 — 自动加入
    final_id = pid if pid else _slug_from_name(name)
    keywords = list(dict.fromkeys(
        [name] +
        (raw.get("matchRule", "") or "").replace("domain:", "").replace("port:", "").replace("path:", "").replace(":", " ").split() +
        (raw.get("address", raw.get("url", "")) or "").replace("https://", "").replace("http://", "").replace("/", " ").replace(".", " ").split()
    ))[:8]
    new_platform = {
        "id": final_id,
        "name": name,
        "keywords": keywords,
        "purpose": raw.get("message") or raw.get("note", f"{name}管理系统"),
        "fields": {"username": "账号", "password": "密码", "captcha": "图形验证码"},
        "captchaAuto": raw.get("captchaEngine", raw.get("captchaAuto")) in (True, "ddddocr", "onnx", "paddleocr"),
    }
    PLATFORMS.append(new_platform)
    _save_platforms()
    print(f"[eco-bridge] AI 自动添加平台: {name} (id={final_id})", file=sys.stderr)
    return {"matched": True, "platform": new_platform}


def _slug_from_name(name: str) -> str:
    """从中文平台名生成拼音风格 id。"""
    import re
    # 简单处理：取中文转拼音或直接用英文/数字
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "_", name.lower())[:20].strip("_")
    if not s:
        s = f"p{len(PLATFORMS)+1}"
    return s


def _placeholder_captcha() -> dict:
    """生成模拟图形验证码（4位字母数字 + 干扰线），返回 base64 PNG。
    用于占位模式和 Hermes 未返回图片时的兜底。"""
    import base64, io, random, string
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        code = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
        return {"mode": "ai", "value": code}

    code = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=4))
    w, h = 140, 44
    img = Image.new('RGB', (w, h), (240, 238, 229))
    draw = ImageDraw.Draw(img)
    for _ in range(5):
        x1, y1 = random.randint(0, w), random.randint(0, h)
        x2, y2 = random.randint(0, w), random.randint(0, h)
        draw.line((x1, y1, x2, y2), fill=(180, 170, 155), width=1)
    for _ in range(30):
        draw.point((random.randint(0, w), random.randint(0, h)), fill=(200, 190, 175))
    try:
        font = ImageFont.truetype(
            '/System/Library/Fonts/Helvetica.ttc', 22
        ) if os.path.exists('/System/Library/Fonts/Helvetica.ttc') else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    for i, ch in enumerate(code):
        x = 8 + i * 32 + random.randint(-3, 3)
        y = random.randint(2, 10)
        r, g, b = random.randint(40, 80), random.randint(30, 80), random.randint(70, 120)
        draw.text((x, y), ch, fill=(r, g, b), font=font)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()
    return {"mode": "manual", "imageB64": b64}


def _normalize_captcha_result(raw: dict) -> dict:
    """归一化验证码结果为 {mode: "ai"|"manual", value?, imageB64?}"""
    # Hermes 原始返回格式多变，先扁平化：
    # 变体A: {mode: "manual"} — 占位
    # 变体B: {captcha: {recognized: {captchaText, confidence}, image: "..."}}
    # 变体C: {action, platformId, mode: "test"|"real", imageBase64: "...", ok: true}
    # 变体D: 已是标准格式 {mode, value?, imageB64?}
    cap = raw.get("captcha", {})
    if cap:
        # 变体B — 嵌套 captcha 对象
        rec = cap.get("recognized", {})
        text = rec.get("captchaText", "")
        conf = rec.get("confidence", 0)
        img = cap.get("image", "")
        if text and conf > 0.7:
            return {"mode": "ai", "value": text, "confidence": conf, "imageB64": img}
        if text:
            return {"mode": "ai", "value": text, "confidence": conf, "imageB64": img}
        if img:
            return {"mode": "manual", "imageB64": img}
        return {"mode": "manual"}

    # 变体C / 已经是标准格式
    mode = raw.get("mode", "")
    if mode in ("ai", "manual"):
        # 已经是标准格式，但 imageBase64 可能叫法不同
        img = raw.get("imageB64") or raw.get("imageBase64") or ""
        val = raw.get("value", raw.get("recognizedText", ""))
        return {"mode": mode, "value": val, "imageB64": img}

    # mode = "test" / "real" / 其他 Hermes 模式
    img = raw.get("imageB64") or raw.get("imageBase64") or ""
    val = raw.get("value") or raw.get("recognizedText") or raw.get("captchaText") or ""
    if val or img:
        return {"mode": "ai" if val else "manual", "value": val, "imageB64": img}

    return {"mode": "manual"}


def _normalize_login_result(raw: dict) -> dict:
    """归一化登录接管结果为 {ok: bool, status: str, message?: str}"""
    # 已经是标准格式
    if "ok" in raw:
        return raw

    # Hermes 真实模式：{action, status: "SESSION_TAKEOVER"/"FAILED"/..., message: "登录成功..."}
    status = (raw.get("status") or "").upper()
    message = (raw.get("message") or raw.get("note") or "")
    # 多种成功信号：status 标准值 / 消息含「成功」
    ok = status in ("SESSION_TAKEOVER", "AI_MANAGED", "OK", "SUCCESS") or \
         ("成功" in message and "失败" not in message and "错误" not in message)
    return {
        "ok": ok,
        "status": "ai_managed" if ok else "error",
        "message": message,
    }

_SESSION_LOCK = threading.Lock()
SESSIONS: dict[str, str] = {}


# ═══════════════════════════════════════════════════════════════════
# call_hermes() — 核心桥接函数
# ═══════════════════════════════════════════════════════════════════

def call_hermes(action: str, params: dict | None = None) -> dict:
    """向 Hermes agent 基座发起调用并返回结构化结果。

    这是 eco-bridge 唯一的外部调用入口——所有 AI 能力（地址识别、验证码、
    登录代填、文书生成、审阅批注）都通过本函数委托给 Hermes agent 核心。
    本函数绝不实现任何 AI 逻辑。

    双模运行：
      - 占位模式（默认）：返回合理模拟数据，保证前端链路不断
      - 真实模式（HERMES_REAL=1）：通过 subprocess 或 import 调用 Hermes
    """
    p = params or {}
    real_mode = os.getenv("HERMES_REAL")

    # ── 占位实现（HERMES_REAL=0 或加载失败时使用） ──
    if real_mode != "1":
        return _call_hermes_placeholder(action, p)

    # ── 真实 Hermes 调用 ──
    try:
        return _call_hermes_real(action, p)
    except Exception as exc:
        print(f"[eco-bridge] Hermes 调用失败 ({action}): {exc}，回落占位")
        return _call_hermes_placeholder(action, p)


def _call_hermes_placeholder(action: str, p: dict) -> dict:
    """占位实现：保证前后端链路不断，返回合理模拟数据。"""
    now = datetime.now(timezone.utc).isoformat()

    if action == "match_platform":
        addr = (p.get("address") or "").strip().lower()
        if not addr:
            return {"matched": False, "reason": "地址为空"}
        for plat in PLATFORMS:
            kws = [k.lower() for k in plat.get("keywords", [])]
            if addr == plat.get("url") or any(k and k in addr for k in kws):
                return {"matched": True, "platform": plat}
        return {"matched": False, "reason": "不在白名单内"}

    if action == "get_captcha":
        return _placeholder_captcha()

    if action == "login_and_takeover":
        return {"ok": True, "status": "ai_managed", "message": "已接管，后续由 AI 日常代管"}

    if action == "auth_health":
        return _probe_auth_health(p.get("platform_id", "atmosphere"))

    if action == "auth_login":
        platform_id = p.get("platform_id", "atmosphere")
        # 占位：模拟登录成功
        os.makedirs(STATE_DIR, exist_ok=True)
        ledger = {
            "lastCredentialAuthAt": now,
            "authMode": "credential_verified",
            "status": "ok",
        }
        with open(os.path.join(STATE_DIR, f"{platform_id}.json"), "w") as f:
            json.dump(ledger, f, indent=2, ensure_ascii=False)
        return {"ok": True, "status": "ai_managed", "platform": platform_id}

    if action == "office_open":
        doc_id = p.get("docId", "mock-doc-001")
        return {
            "docState": {
                "docId": doc_id,
                "templateId": p.get("templateId", "38"),
                "fileName": p.get("fileName", "行政处罚决定书_草稿.docx"),
                "mode": "reading",
                "status": "editing",
                "paragraphs": _mock_paragraphs(),
                "annotations": _mock_annotations(),
                "onlineUsers": [{"id": "user:admin", "displayName": "李建国", "role": "human"}],
                "aiSync": {"status": "idle", "writingParagraphId": None, "syncedAt": now},
                "openedAt": now,
                "updatedAt": now,
                "version": 1,
            },
        }

    if action == "office_ai_review":
        doc_id = p.get("docId", "")
        return {
            "taskId": f"task-{secrets.token_hex(6)}",
            "estimatedSeconds": 30,
            "status": "started",
            "updates": [
                {"paragraphId": "p-002", "text": "[AI 建议] 把'多次超标'改为'24次超标，1:1对应工况标记'，增强事实认定力度。", "aiMarked": True, "aiAuthor": "文书成"},
                {"paragraphId": "p-005", "text": "[AI 建议] 补充引用的具体条文内容，便于当事人理解违法依据。", "aiMarked": True, "aiAuthor": "法条通"},
            ],
        }

    if action == "office_sync":
        return {"ok": True, "version": p.get("expectedVersion", 1) + 1}

    if action == "gis_latest":
        return {
            "operations": [
                {"id": "gis-1", "time": "10:24", "expert": "数据芯", "description": "在金竹山矿业排口添加超标标注（红色）", "canUndo": True},
                {"id": "gis-2", "time": "10:31", "expert": "执法准", "description": "规划复查路线：3 个点位，全程 18 公里", "canUndo": True},
            ],
        }

    if action == "hermes_memory":
        return {
            "totalLearned": 3,
            "totalRevised": 1,
            "totalReused": 56,
            "cards": [
                {"id": "mem-1", "title": "CEMS 夜间超标 + 用电骤降 = 旁路排放嫌疑", "category": "inspection_point", "status": "verified", "usageCount": 56},
                {"id": "mem-2", "title": "砖瓦企业听证期限易漏算", "category": "procedure_note", "status": "verifying", "usageCount": 12},
            ],
        }

    if action == "office_review_stats":
        return {
            "totalReviewed": 73, "totalTarget": 100, "passRate": 93.2, "deniedCount": 1,
            "trend": {"weeks": ["W27","W28","W29","W30","W31","W32","W33","W34","W35","W36","W37","W38"],
                       "rates": [91,90,92,93,94,93,92,94,93,93,94,93]},
            "vetoDist": [
                {"category": "程序类", "total": 10, "hit": 4},
                {"category": "证据类", "total": 5, "hit": 1},
                {"category": "法律适用", "total": 3, "hit": 1},
                {"category": "移送处理", "total": 4, "hit": 0},
                {"category": "其他", "total": 3, "hit": 0},
            ],
            "alerts": {"pendingReview": 2, "nearDeadline": 1},
        }

    if action == "chat":
        user_msg = p.get("message", "")
        model_id = p.get("model", "deepseek-v4")
        history = p.get("history", [])
        # 占位：返回自然回复，不暴露内部配置
        return {
            "reply": f"你好，我是 EcoAegis 执法助理，以《生态环境法典》（2026.8.15施行）为法律基石。\n\n你的问题「{user_msg[:60]}」已收到。我可以帮你：\n- 查法规（法典5编1242条 + 新旧法比对）\n- 起草文书（处罚决定书/告知书/笔录等）\n- 案卷评查（程序合法性/证据链/法律适用）\n- 执法流程指导（立案→调查→告知→决定→执行）\n\n请告诉我你需要什么具体帮助？",
            "model": model_id,
            "tokens": len(user_msg) * 3,
            "timestamp": now,
        }

    return {"error": f"未知 action: {action}"}


def _call_hermes_real(action: str, p: dict) -> dict:
    """真实 Hermes 调用：通过 venv Python 3.11+ + run_agent.AIAgent 调用。

    eco-bridge 运行在系统 Python 3.9，而 Hermes agent 需要 Python 3.11+，
    因此通过 subprocess + venv python + -c 内联脚本的方式调用 run_agent.AIAgent。
    """
    venv_python = _find_hermes_python()
    if not venv_python:
        raise RuntimeError("找不到 Hermes agent 的 Python 3.11+ 环境")

    return _call_hermes_via_agent(action, p, python_bin=venv_python)


def _call_hermes_via_agent(action: str, p: dict, python_bin: str) -> dict:
    """通过 subprocess 调用 hermes_runner.py 脚本。

    hermes_runner.py 在 Python 3.11+ venv 中运行，import run_agent.AIAgent，
    构造 prompt 后调用 chat() 并返回 JSON。
    """
    runner = os.path.join(HERE, "hermes_runner.py")
    payload = json.dumps({"action": action, "params": p}, ensure_ascii=False)

    result = subprocess.run(
        [python_bin, runner, payload],
        capture_output=True,
        text=True,
        timeout=45,
        cwd=HERE,
    )

    if result.returncode != 0:
        print(f"[eco-bridge] Hermes runner 失败 (exit={result.returncode})", file=sys.stderr)
        print(f"[eco-bridge] STDERR: {result.stderr[-2000:]}", file=sys.stderr)
        raise RuntimeError(f"Hermes runner 返回非零: {result.stderr[-500:]}")

    # 打印 hermes_runner 的 stderr 日志（含 system prompt、token 统计）
    if result.stderr:
        for line in result.stderr.strip().split("\n"):
            if line.startswith("[hermes-runner]"):
                print(line, file=sys.stderr, flush=True)

    return _parse_hermes_output(result.stdout, result.stderr)


def _parse_hermes_output(stdout: str, stderr: str) -> dict:
    """从 Hermes runner 的输出中提取 JSON 结果。

    AIAgent 的日志输出到 stderr，结果输出到 stdout。
    但有时 JSON 会混在 stderr 中，需要综合考虑。
    """
    # 优先从 stdout 解析
    if stdout.strip():
        try:
            return json.loads(stdout.strip().split("\n")[-1])
        except (json.JSONDecodeError, ValueError):
            pass

    # 从 stderr 中找最后的 JSON 行
    for line in reversed(stderr.strip().split("\n")):
        try:
            return json.loads(line.strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # 回退到非 JSON 输出
    last_line = (stdout.strip() or stderr.strip()).split("\n")[-1][:500]
    print(f"[eco-bridge] Hermes 输出解析失败: {last_line}")
    return {"raw": last_line, "warning": "Hermes 返回非结构化文本"}


def _find_hermes_python() -> str | None:
    """查找 Hermes agent 的 Python 3.11+ 环境路径。

    优先级:
      1. HERMES_PYTHON 环境变量
      2. ~/.hermes/hermes-agent/venv/bin/python3
      3. 扫描常见路径
    """
    venv = os.getenv("HERMES_PYTHON")
    if venv and os.path.isfile(venv):
        return venv

    candidates = [
        os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python3.11"),
        os.path.expanduser("~/.hermes/hermes-agent/venv/bin/python3"),
        os.path.expanduser("~/.local/bin/python3.12"),
        os.path.expanduser("~/.local/bin/python3.11"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            # 验证版本 >= 3.10
            try:
                r = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=5)
                ver = r.stdout.strip() + r.stderr.strip()
                if "3.1" in ver or "3.12" in ver or "3.13" in ver:
                    print(f"[eco-bridge] 使用 Hermes Python: {c} ({ver})")
                    return c
            except Exception:
                pass
    return None


def _call_hermes_import(action: str, p: dict) -> dict:
    """通过 run_agent.AIAgent 直接调用 Hermes agent 的 AI 能力。

    注意：此方法仅在 eco-bridge 运行在 Python 3.11+ 时可用。
    当前系统 Python 3.9 环境下会跳过此路径，改用 CLI subprocess 模式。
    """
    import sys
    hermes_path = os.path.join(PROJECT_ROOT, "hermes-agent")
    if hermes_path not in sys.path:
        sys.path.insert(0, hermes_path)

    from run_agent import AIAgent

    system_msg = (
        "你是 EcoAegis 环保执法办案系统的 AI 引擎，通过 eco-bridge 被前端调用。"
        "你需要执行以下动作并返回结构化 JSON 结果。"
        "只返回 JSON，不要附加任何解释文字。"
    )
    user_msg = json.dumps({"action": action, "params": p}, ensure_ascii=False)

    agent = AIAgent(max_iterations=5)
    raw = agent.chat(f"{system_msg}\n\n用户请求: {user_msg}")

    raw_stripped = raw.strip()
    if raw_stripped.startswith("```"):
        lines = raw_stripped.split("\n")
        raw_stripped = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        return json.loads(raw_stripped)
    except json.JSONDecodeError:
        print(f"[eco-bridge] Hermes 返回非 JSON，原文: {raw[:200]}")
        return {"raw": raw, "warning": "Hermes 返回非结构化文本，请检查 model 配置"}


def _call_hermes_cli(action: str, p: dict, python_bin: str = "python3") -> dict:
    """通过 Hermes CLI subprocess 调用。

    使用 hermes-agent/cli.py 的 -z (oneshot) 模式 —— 单次问答，不进入交互循环。
    """
    cli_entry = os.path.join(PROJECT_ROOT, "hermes-agent", "cli.py")
    payload = json.dumps({"action": action, "params": p}, ensure_ascii=False)

    cmd = [
        python_bin, cli_entry,
        "-z",
        f"EcoAegis eco-bridge 请求: 执行动作 '{action}'，参数: {payload}。仅返回 JSON，不要附加任何解释文字。",
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120,
        cwd=os.path.join(PROJECT_ROOT, "hermes-agent"),
    )
    if result.returncode != 0:
        raise RuntimeError(f"Hermes CLI 返回非零 ({result.returncode}): {result.stderr[-500:]}")

    stdout = result.stdout.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[\s\S]*\}', stdout)
        if match:
            return json.loads(match.group())
        print(f"[eco-bridge] CLI 输出非 JSON，原文: {stdout[:200]}")
        return {"raw": stdout, "warning": "Hermes CLI 返回非结构化文本"}


# ═══════════════════════════════════════════════════════════════════
# Auth 探针
# ═══════════════════════════════════════════════════════════════════

def _probe_auth_health(platform_id: str) -> dict:
    """检测平台认证状态。读取心跳账本 + storageState 文件。"""
    ledger_path = os.path.join(STATE_DIR, f"{platform_id}.json")
    state_path = os.path.join(STATE_DIR, f"{platform_id}.storageState.json")

    if not os.path.exists(state_path):
        return {
            "platform": platform_id,
            "status": "NO_STATE",
            "severity": "critical",
            "message": f"{platform_id} 从未成功登录，storageState 不存在",
            "checkedAt": datetime.now(timezone.utc).isoformat(),
        }

    # 检查会话是否过期
    try:
        with open(ledger_path) as f:
            ledger = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        ledger = {}

    last_auth = ledger.get("lastCredentialAuthAt", "")
    days_since = 0
    if last_auth:
        try:
            last_dt = datetime.fromisoformat(last_auth.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - last_dt).days
        except (ValueError, TypeError):
            pass

    if days_since > 7:
        return {
            "platform": platform_id,
            "status": "SESSION_EXPIRED",
            "severity": "critical",
            "lastAuth": last_auth,
            "daysSince": days_since,
            "message": f"会话已过期 {days_since} 天，需重新登录",
            "checkedAt": datetime.now(timezone.utc).isoformat(),
        }
    if days_since > 3:
        return {
            "platform": platform_id,
            "status": "SESSION_WARN",
            "severity": "warning",
            "lastAuth": last_auth,
            "daysSince": days_since,
            "message": f"会话即将过期（{days_since} 天），建议尽快续期",
            "checkedAt": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "platform": platform_id,
        "status": "SESSION_VALID",
        "severity": "ok",
        "lastAuth": last_auth,
        "daysSince": days_since,
        "authMode": ledger.get("authMode", "unknown"),
        "message": "认证状态正常",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════
# Mock 数据
# ═══════════════════════════════════════════════════════════════════

def _mock_paragraphs() -> list[dict]:
    return [
        {"id": "p-001", "index": 1, "text": "我厅（局）于 2026年7月15日 对你（单位）进行了调查…", "aiMarked": False},
        {"id": "p-002", "index": 2, "text": "CEMS数据显示…涉嫌通过工况标记造假规避超标记录。", "aiMarked": True, "aiAuthor": "文书成", "aiRevision": "原调查报告仅记录超标事实。"},
        {"id": "p-003", "index": 3, "text": "以上事实，有以下主要证据证明：", "aiMarked": False},
        {"id": "p-004", "index": 4, "text": "1. 营业执照…\n2. CEMS工况标记历史数据…\n3. CEMS分钟级数据…", "aiMarked": True, "aiAuthor": "文书成"},
        {"id": "p-005", "index": 5, "text": "你（单位）的上述行为违反了《中华人民共和国生态环境法典》污染防治编·大气污染防治分编关于超标排放大气污染物的规定（原《大气污染防治法》第18条，已废止）。", "aiMarked": True, "aiAuthor": "法条通"},
    ]


def _mock_annotations() -> list[dict]:
    return [
        {
            "id": "ann-001", "paragraphId": "p-002", "rangeStart": 0, "rangeEnd": 45,
            "author": {"id": "agent:wenshucheng", "displayName": "文书成", "role": "ai", "color": "#C97C3E"},
            "content": "第2段新增'涉嫌通过工况标记造假'措辞，请核实是否符合实际违法情形。",
            "createdAt": "2026-08-08T08:15:00Z",
            "replies": [{"id": "rep-001", "annotationId": "ann-001", "author": {"id": "user:admin", "displayName": "李建国", "role": "human"}, "content": "确认数据准确，采用。", "createdAt": "2026-08-08T08:22:00Z"}],
            "resolved": False,
        },
        {
            "id": "ann-002", "paragraphId": "p-005", "rangeStart": 0, "rangeEnd": 30,
            "author": {"id": "user:admin", "displayName": "李建国", "role": "human", "color": "#5B6C85"},
            "content": "罚款金额需核对自由裁量基准中的档位设置。",
            "createdAt": "2026-08-08T08:25:00Z",
            "replies": [{"id": "rep-002", "annotationId": "ann-002", "author": {"id": "agent:wenshucheng", "displayName": "文书成", "role": "ai"}, "content": "已按基准计算：50万 × 从轻5% = 47.5万。", "createdAt": "2026-08-08T08:26:00Z"}],
            "resolved": True, "resolvedBy": "user:admin", "resolvedAt": "2026-08-08T08:27:00Z",
        },
    ]


# ═══════════════════════════════════════════════════════════════════
# HTTP Handler
# ═══════════════════════════════════════════════════════════════════

class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b"{}"
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[eco-bridge {ts}] {msg}")

    def _handle_platform_add(self, payload: dict) -> None:
        """新增平台到白名单，持久化写入 platforms.json。"""
        name = (payload.get("name") or "").strip()
        purpose = (payload.get("purpose") or "").strip()
        if not name:
            return self._send(400, {"error": "平台名称不能为空"})
        if not purpose:
            return self._send(400, {"error": "平台用途不能为空"})

        # 生成 id：取 name 拼音首字母或英文部分
        raw_id = payload.get("id", "").strip()
        if not raw_id:
            import re
            raw_id = re.sub(r"[^a-zA-Z0-9_]", "_", name.lower())[:20].strip("_") or f"p{len(PLATFORMS)+1}"

        # 防止重复 id
        for p in PLATFORMS:
            if p["id"] == raw_id:
                raw_id = f"{raw_id}_{secrets.token_hex(3)}"
                break

        new_platform = {
            "id": raw_id,
            "name": name,
            "keywords": payload.get("keywords", []) or [name] or [raw_id],
            "purpose": purpose,
            "fields": payload.get("fields") or {"username": "账号", "password": "密码", "captcha": "图形验证码"},
            "captchaAuto": payload.get("captchaAuto", False),
        }

        PLATFORMS.append(new_platform)
        _save_platforms()
        self._log(f"新增平台: {name} (id={raw_id})")
        return self._send(200, {"ok": True, "platform": new_platform})

    def _handle_platform_delete(self, payload: dict) -> None:
        """从白名单中删除平台。"""
        pid = (payload.get("id") or "").strip()
        if not pid:
            return self._send(400, {"error": "平台 id 不能为空"})
        global PLATFORMS
        PLATFORMS = [p for p in PLATFORMS if p["id"] != pid]
        _save_platforms()
        self._log(f"删除平台: {pid}")
        return self._send(200, {"ok": True, "removed": pid})

    # ── 反向代理（绕过 X-Frame-Options，用于 iframe 嵌入外部平台）──
    def _handle_proxy(self, target_url: str) -> None:
        """抓取目标页面，剥离 X-Frame-Options / CSP frame-ancestors，注入 <base> 标签。"""
        # CVE-02: scheme + 域名白名单，防止 SSRF/LFI
        pu = urlparse(target_url)
        if pu.scheme not in ("http", "https"):
            self._send(400, {"error": "仅支持 http/https 协议", "scheme": pu.scheme})
            return
        # 默认拒绝：必须设置 ECO_BRIDGE_PROXY_ALLOW 才能启用代理（CVE-02 残留修复）
        allowed_hosts = os.getenv("ECO_BRIDGE_PROXY_ALLOW", "")
        if not allowed_hosts:
            self._send(403, {"error": "代理未配置白名单，请设置 ECO_BRIDGE_PROXY_ALLOW 环境变量"})
            return
        allowed = [h.strip() for h in allowed_hosts.split(",") if h.strip()]
        if not any(pu.hostname == h or pu.hostname.endswith("." + h) for h in allowed):
            self._send(403, {"error": "主机不在白名单内", "host": pu.hostname})
            return

        self._log(f"proxy → {target_url[:80]}")
        try:
            req = UrlRequest(target_url, headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
            # CVE-02: 恢复 TLS 证书校验
            ctx = _ssl.create_default_context()
            with urlopen(req, timeout=30, context=ctx) as resp:
                body = resp.read()
                content_type = resp.headers.get("Content-Type", "text/html")

                # 转发状态码
                self.send_response(resp.status)

                # 转发响应头，但剥离安全限制头 + chunked 编码
                for key, val in resp.headers.items():
                    kl = key.lower()
                    # 阻止 iframe 嵌入的关键头 —— 全部剥离
                    if kl in ("x-frame-options", "x-content-security-policy",
                              "x-webkit-csp", "strict-transport-security"):
                        continue
                    # 传输编码 —— 由我们重新计算 Content-Length，不转发 chunked
                    if kl in ("transfer-encoding",):
                        continue
                    # CSP：只移除 frame-ancestors 指令，保留其他安全策略
                    if kl == "content-security-policy":
                        cleaned = re.sub(
                            r"frame-ancestors\s+[^;]+;?\s*", "",
                            val, flags=re.I,
                        ).strip()
                        if not cleaned:
                            continue
                        val = cleaned
                    self.send_header(key, val)

                # 注入 <base> 标签，让页面内相对路径资源指向原始服务器
                if content_type and "text/html" in content_type:
                    body_str = body.decode("utf-8", errors="replace")
                    pu = urlparse(target_url)
                    base_url = f"{pu.scheme}://{pu.netloc}/"
                    base_tag = f'<base href="{base_url}">'
                    if "<head" in body_str.lower():
                        body_str = re.sub(
                            r"(<head\b[^>]*>)", rf"\1{base_tag}",
                            body_str, count=1, flags=re.I,
                        )
                    else:
                        body_str = base_tag + body_str
                    body = body_str.encode("utf-8")

                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
        except HTTPError as e:
            self._send(e.code, {"error": f"upstream returned {e.code}"})
        except URLError as e:
            self._send(502, {"error": f"unreachable: {e.reason}"})
        except Exception as e:
            self._send(500, {"error": f"proxy failed: {e}"})

    # ── SSE 流式响应 ──
    def _handle_chat_stream(self, payload: dict) -> None:
        """建立 SSE 连接，逐字流式推送 AI 对话回复。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        user_msg = payload.get("message", "")
        model_id = payload.get("model", "deepseek-v4")
        history = payload.get("history", [])

        # 调用 Hermes chat（占位 / 真实双模）
        result = call_hermes("chat", {
            "message": user_msg,
            "model": model_id,
            "history": history,
        })

        reply = result.get("reply", "")
        model = result.get("model", model_id)
        tokens = result.get("tokens", 0)

        # 流式逐字推送回复文本
        for i in range(0, len(reply), 3):
            chunk = reply[i:i + 3]
            line = f"event: chunk\ndata: {json.dumps({'text': chunk, 'index': i}, ensure_ascii=False)}\n\n"
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()
            time.sleep(0.03)

        # 推送完成事件
        done = f"event: done\ndata: {json.dumps({'model': model, 'tokens': tokens}, ensure_ascii=False)}\n\n"
        self.wfile.write(done.encode("utf-8"))
        self.wfile.flush()

    def _handle_chat_feedback(self, payload: dict) -> None:
        """对话反馈埋点 — 记录用户对 AI 回复的赞/踩事件。"""
        msg_id = payload.get("msgId", "?")
        feedback_type = payload.get("type", "?")
        msg_preview = (payload.get("msgText") or "")[:80]
        ts = datetime.now(timezone.utc).isoformat()

        log_line = (
            f"[chat-feedback] id={msg_id} "
            f"type={feedback_type} "
            f"preview=\"{msg_preview}\" "
            f"ts={ts}"
        )
        # 写入 stderr 供运维采集（亦可转发到日志平台）
        sys.stderr.write(log_line + "\n")
        sys.stderr.flush()

        self._send(200, {"ok": True, "logged": True})

    def _handle_resize_log(self, payload: dict) -> None:
        """面板拖拽埋点 — 记录左右侧栏宽度拖拽变化。"""
        panel = payload.get("panel", "?")
        width = payload.get("width", 0)
        phase = payload.get("phase", "?")
        ts = payload.get("ts", datetime.now(timezone.utc).isoformat())

        log_line = f"[resize] panel={panel} phase={phase} width={width}px ts={ts}"
        sys.stderr.write(log_line + "\n")
        sys.stderr.flush()

        self._send(200, {"ok": True, "logged": True})

    def _handle_sse_stream(self, route: str, payload: dict) -> None:
        """建立 SSE 连接，逐步推送 AI 进度事件。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("X-Accel-Buffering", "no")  # 禁用 nginx 缓冲
        self.end_headers()

        doc_id = payload.get("docId", "stream-doc")
        event_q: queue.Queue = queue.Queue()

        def run_ai():
            """在后台线程中执行 AI 审阅，通过队列推送进度事件。"""
            try:
                # 阶段 1：分析
                _sse_send(event_q, "progress", {"percent": 10, "message": "正在加载文书结构..."})
                time.sleep(0.3)

                steps = [
                    (25, "正在分析段落逻辑..."),
                    (40, "正在匹配适用法规..."),
                    (55, "正在生成审阅建议..."),
                    (70, "正在校验事实认定..."),
                    (85, "正在整理审阅报告..."),
                ]
                for percent, msg in steps:
                    _sse_send(event_q, "progress", {"percent": percent, "message": msg})
                    time.sleep(0.4)

                # 阶段 2：调用 Hermes AI 生成建议
                _sse_send(event_q, "progress", {"percent": 90, "message": "AI 引擎生成中..."})
                result = call_hermes("office_ai_review", {
                    "docId": doc_id,
                    "reviewType": payload.get("reviewType", "full"),
                    "paragraphIds": payload.get("paragraphIds", []),
                })

                # 阶段 3：逐条推送审阅建议
                updates = result.get("updates", [])
                for i, update in enumerate(updates):
                    _sse_send(event_q, "update", {
                        "paragraphId": update.get("paragraphId", f"p-{i}"),
                        "text": update.get("text", ""),
                        "aiMarked": True,
                        "aiAuthor": update.get("aiAuthor", "EcoAegis-AI"),
                        "index": i + 1,
                        "total": len(updates),
                    })
                    time.sleep(0.5)

                # 阶段 4：完成
                _sse_send(event_q, "done", {
                    "status": "completed",
                    "taskId": result.get("taskId", f"task-{secrets.token_hex(6)}"),
                    "totalSuggestions": len(updates),
                    "reviewedAt": datetime.now(timezone.utc).isoformat(),
                })

            except Exception as exc:
                _sse_send(event_q, "error", {"message": str(exc)})

        threading.Thread(target=run_ai, daemon=True).start()

        # 从队列读取事件并写入 SSE 流
        try:
            while True:
                event = event_q.get(timeout=60)  # 1 分钟超时
                line = f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
                self.wfile.write(line.encode("utf-8"))
                self.wfile.flush()
                if event["event"] in ("done", "error"):
                    break
        except queue.Empty:
            _sse_send(event_q, "error", {"message": "AI 审阅超时"})
            line = f"event: error\ndata: {json.dumps({'message': 'AI 审阅超时'})}\n\n"
            self.wfile.write(line.encode("utf-8"))
            self.wfile.flush()

    # ── CORS 预检 ──
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ── GET 端点 ──
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        qs = {}
        if parsed.query:
            from urllib.parse import parse_qs
            qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        route = parsed.path.rstrip("/")

        # 系统健康检查（CVE-01 配套: 返回各组件状态）
        if route == "/api/health":
            import platform, sys
            health = {
                "status": "ok",
                "service": "eco-bridge",
                "port": PORT,
                "bind": BIND_ADDR,
                "python": sys.version.split()[0],
                "platform": platform.platform()[:60],
            }
            # 检查 auth state 目录
            health["authStateExists"] = os.path.isdir(STATE_DIR)
            if health["authStateExists"]:
                import glob
                states = glob.glob(os.path.join(STATE_DIR, "*.storageState.json"))
                health["storageStateFiles"] = len(states)
            # 检查 enforcement skill 可用性
            skill = _get_enforcement_skill()
            health["enforcementSkill"] = "ok" if "error" not in skill else f"degraded: {skill['error']}"
            # 代理白名单状态
            proxy_allowed = os.getenv("ECO_BRIDGE_PROXY_ALLOW", "")
            health["proxyEnabled"] = bool(proxy_allowed)
            if proxy_allowed:
                health["proxyHosts"] = [h.strip() for h in proxy_allowed.split(",") if h.strip()]
            return self._send(200, health)

        # 认证健康检测
        if route == "/api/auth/health":
            pid = qs.get("platform", "atmosphere")
            return self._send(200, call_hermes("auth_health", {"platform_id": pid}))

        # 全部平台健康
        if route == "/api/auth/health-all":
            results = {}
            for pid in ("atmosphere", "water"):
                results[pid] = call_hermes("auth_health", {"platform_id": pid})
            return self._send(200, {"platforms": results})

        # 文书状态查询
        if route == "/api/office/state":
            doc_id = qs.get("docId", "")
            if not doc_id:
                return self._send(400, {"error": "缺少 docId"})
            return self._send(200, call_hermes("office_open", {"docId": doc_id}))

        # 评查看板数据
        if route == "/api/office/review-stats":
            return self._send(200, call_hermes("office_review_stats", {}))

        # GIS 最近操作
        if route == "/api/gis/latest":
            limit = int(qs.get("limit", "20"))
            result = call_hermes("gis_latest", {"limit": limit})
            return self._send(200, result)

        # Hermes 记忆进化数据
        if route == "/api/hermes/memory":
            return self._send(200, call_hermes("hermes_memory", {}))

        # 反向代理（剥离 X-Frame-Options，用于 iframe 嵌入外部平台）
        if route == "/api/proxy":
            target = qs.get("url", "")
            if not target:
                return self._send(400, {"error": "missing url parameter"})
            return self._handle_proxy(target)

        # ═══ /api/enforcement/* — 执法办案 Skill ═══

        # 获取案卷列表
        if route == "/api/enforcement/cases":
            return self._handle_enforcement_get_cases(qs)

        # 获取案卷详情
        if route == "/api/enforcement/case-detail":
            return self._handle_enforcement_get_case_detail(qs)

        # 获取文书列表
        if route == "/api/enforcement/documents":
            return self._handle_enforcement_get_documents(qs)

        # 下载单份文书
        if route == "/api/enforcement/document-download":
            return self._handle_enforcement_document_download(qs)

        # 获取企业列表
        if route == "/api/enforcement/enterprises":
            return self._handle_enforcement_get_enterprises(qs)

        return self._send(404, {"error": "not found"})

    # ── POST 端点 ──
    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/")
        payload = self._read_body()

        self._log(f"POST {route}")

        # ═══ SSE 流式端点 — 在常规路由之前 ═══

        if route == "/api/stream/ai-review":
            return self._handle_sse_stream("/api/stream/ai-review", payload)

        # AI 对话流（流式逐字输出）
        if route == "/api/stream/chat":
            return self._handle_chat_stream(payload)

        # 对话反馈埋点（赞/踩）
        if route == "/api/chat/feedback":
            return self._handle_chat_feedback(payload)

        # 面板拖拽埋点（左右侧栏宽度变化）
        if route == "/api/resize/log":
            return self._handle_resize_log(payload)

        # ═══ /api/platform/* — 平台接入三步 ═══

        if route == "/api/platform/match":
            address = payload.get("address", "")
            # 1) 优先本地关键词匹配（快速且稳定）
            result = _call_hermes_placeholder("match_platform", {"address": address})
            if result.get("matched"):
                return self._send(200, _normalize_match_result(result))
            # 2) 本地未命中，委托 Hermes AI 做语义识别
            result = call_hermes("match_platform", {"address": address})
            return self._send(200, _normalize_match_result(result))

        if route == "/api/platform/captcha":
            sid = payload.get("sessionToken") or secrets.token_hex(8)
            with _SESSION_LOCK:
                SESSIONS[sid] = payload.get("platformId")
            result = call_hermes("get_captcha", {"platformId": payload.get("platformId"), "sessionToken": sid})
            return self._send(200, _normalize_captcha_result(result))

        if route == "/api/platform/login":
            sid = payload.get("sessionToken")
            with _SESSION_LOCK:
                SESSIONS.pop(sid, None)
            result = call_hermes("login_and_takeover", {
                "platformId": payload.get("platformId"),
                "username": payload.get("username", ""),
                "password": payload.get("password", ""),
                "captcha": payload.get("captcha", ""),
                "remember": payload.get("remember", False),
                "sessionToken": sid,
            })
            return self._send(200, _normalize_login_result(result))

        # ── 平台 CRUD：新增 / 删除 ──

        if route == "/api/platform/add":
            return self._handle_platform_add(payload)

        if route == "/api/platform/delete":
            return self._handle_platform_delete(payload)

        # ═══ /api/office/* — 文书协同 ═══

        if route == "/api/office/open":
            doc_id = payload.get("docId") or f"doc-{secrets.token_hex(6)}"
            result = call_hermes("office_open", {
                "docId": doc_id,
                "templateId": payload.get("templateId", ""),
                "fileName": payload.get("fileName", ""),
                "userId": payload.get("userId", "user:admin"),
                "userName": payload.get("userName", "李建国"),
            })
            return self._send(200, result)

        if route == "/api/office/ai-review":
            result = call_hermes("office_ai_review", {
                "docId": payload.get("docId", ""),
                "userId": payload.get("userId", ""),
                "reviewType": payload.get("reviewType", "full"),
                "paragraphIds": payload.get("paragraphIds", []),
            })
            return self._send(200, result)

        if route == "/api/office/sync":
            result = call_hermes("office_sync", {
                "docId": payload.get("docId", ""),
                "userId": payload.get("userId", ""),
                "action": payload.get("action", ""),
                "paragraphId": payload.get("paragraphId", ""),
                "text": payload.get("text", ""),
                "expectedVersion": payload.get("expectedVersion"),
            })
            return self._send(200, result)

        if route == "/api/office/annotation":
            return self._send(200, {"ok": True, "annotation": {
                "id": f"ann-{secrets.token_hex(4)}",
                "paragraphId": payload.get("paragraphId", ""),
                "content": payload.get("content", ""),
                "author": {"id": payload.get("userId", "user:admin"), "displayName": payload.get("userName", "李建国"), "role": "human"},
                "createdAt": datetime.now(timezone.utc).isoformat(),
                "replies": [],
                "resolved": False,
            }})

        if route == "/api/office/annotation/reply":
            return self._send(200, {"ok": True, "reply": {
                "id": f"rep-{secrets.token_hex(3)}",
                "annotationId": payload.get("annotationId", ""),
                "content": payload.get("content", ""),
                "author": {"id": payload.get("userId", "user:admin"), "displayName": payload.get("userName", ""), "role": "human"},
                "createdAt": datetime.now(timezone.utc).isoformat(),
            }})

        if route == "/api/office/annotation/resolve":
            return self._send(200, {"ok": True})

        # ═══ /api/auth/* — 认证管理 ═══

        if route == "/api/auth/login":
            result = call_hermes("auth_login", {
                "platform_id": payload.get("platformId", "atmosphere"),
            })
            return self._send(200, result)

        # ═══ /api/enforcement/* — 执法办案 Skill ═══

        # 连接平台（复用 Chrome 会话或 API 登录）
        if route == "/api/enforcement/connect":
            return self._handle_enforcement_connect(payload)

        # 扫描平台模块
        if route == "/api/enforcement/scan":
            return self._handle_enforcement_scan(payload)

        # 全量同步
        if route == "/api/enforcement/sync":
            return self._handle_enforcement_sync(payload)

        # 导出 Excel
        if route == "/api/enforcement/export":
            return self._handle_enforcement_export(payload)

        # 日常巡检
        if route == "/api/enforcement/inspect":
            return self._handle_enforcement_inspect(payload)

        return self._send(404, {"error": "not found", "route": route})

    def log_message(self, *args) -> None:
        return  # 静默

    # ═══════════════════════════════════════════════════════════════
    # 执法办案 Skill 处理器
    # ═══════════════════════════════════════════════════════════════

    # 共享平台实例缓存（session token → EnforcementPlatform）
    _platforms: dict[str, object] = {}

    def _get_platform(self, token: str):
        """根据 session token 获取或创建平台实例"""
        if token not in self._platforms:
            skill = _get_enforcement_skill()
            if "error" in skill:
                return None, {"error": "skill_not_loaded", "detail": skill["error"]}
            self._platforms[token] = skill["create_platform"]()
        return self._platforms[token], None

    def _handle_enforcement_connect(self, payload: dict) -> None:
        """POST /api/enforcement/connect — 连接执法办案平台"""
        token = payload.get("sessionToken") or secrets.token_hex(16)
        jsessionid = payload.get("jsessionid", "")
        mode = payload.get("mode", "chrome")  # "chrome" | "login"

        skill = _get_enforcement_skill()
        if "error" in skill:
            return self._send(500, {"error": "skill_not_loaded", "detail": skill["error"]})

        platform = skill["create_platform"]()

        if mode == "chrome":
            ok = platform.connect_via_chrome(int(payload.get("chromePort", 9222)))
            if not ok:
                return self._send(400, {
                    "ok": False, "error": "chrome_session_not_found",
                    "message": "未找到 Chrome 中的平台会话，请确认已登录平台且 Chrome 启动了调试端口",
                })
        elif mode == "session":
            ok = platform.connect_with_session(jsessionid)
            if not ok:
                return self._send(400, {"ok": False, "error": "session_invalid", "message": "JSESSIONID 无效或已过期"})
        elif mode == "login":
            result = platform.connect(payload.get("username", ""), payload.get("password", ""))
            if not result.get("ok"):
                return self._send(400, result)

        self._platforms[token] = platform
        return self._send(200, {
            "ok": True, "sessionToken": token,
            "message": "已连接湖南生态环境智慧执法办案系统",
        })

    def _handle_enforcement_scan(self, payload: dict) -> None:
        """POST /api/enforcement/scan — 扫描平台模块"""
        platform, err = self._get_platform(payload.get("sessionToken", ""))
        if err:
            return self._send(400, err)
        if not platform.connected:
            return self._send(400, {"error": "not_connected", "message": "请先调用 /api/enforcement/connect"})

        try:
            manifest = platform.scan()
            return self._send(200, {"ok": True, "manifest": asdict(manifest)})
        except Exception as e:
            return self._send(500, {"error": "scan_failed", "message": str(e)})

    def _handle_enforcement_sync(self, payload: dict) -> None:
        """POST /api/enforcement/sync — 全量同步数据"""
        platform, err = self._get_platform(payload.get("sessionToken", ""))
        if err:
            return self._send(400, err)
        if not platform.connected:
            return self._send(400, {"error": "not_connected"})

        try:
            output_dir = _sanitize_output_path(payload.get("outputDir", "/tmp/eco-aegis-sync"))
            result = platform.sync_all(output_dir)
            return self._send(200, {"ok": True, **result})
        except Exception as e:
            return self._send(500, {"error": "sync_failed", "message": str(e)})

    def _handle_enforcement_export(self, payload: dict) -> None:
        """POST /api/enforcement/export — 导出 Excel"""
        platform, err = self._get_platform(payload.get("sessionToken", ""))
        if err:
            return self._send(400, err)
        if not platform.connected:
            return self._send(400, {"error": "not_connected"})

        try:
            module = payload.get("module", "case_ledger")
            save_path = _sanitize_output_path(payload.get("savePath") or "/tmp/eco-aegis-export/export.xlsx")
            path = platform.export_excel(module, save_path)
            return self._send(200, {"ok": True, "file": path, "module": module})
        except Exception as e:
            return self._send(500, {"error": "export_failed", "message": str(e)})

    def _handle_enforcement_inspect(self, payload: dict) -> None:
        """POST /api/enforcement/inspect — 日常巡检"""
        platform, err = self._get_platform(payload.get("sessionToken", ""))
        if err:
            return self._send(400, err)
        if not platform.connected:
            return self._send(400, {"error": "not_connected"})

        try:
            last_sync = payload.get("lastSyncPath")
            report = platform.inspect(last_sync)
            return self._send(200, {"ok": True, "report": asdict(report)})
        except Exception as e:
            return self._send(500, {"error": "inspect_failed", "message": str(e)})

    def _handle_enforcement_get_cases(self, qs: dict) -> None:
        """GET /api/enforcement/cases — 获取案卷列表"""
        platform, err = self._get_platform(qs.get("token", ""))
        if err:
            return self._send(400, err)
        if not platform.connected:
            return self._send(400, {"error": "not_connected"})

        try:
            page = int(qs.get("page", 1))
            rows = int(qs.get("rows", 20))
            result = platform.get_cases(page=page, rows=rows)
            return self._send(200, {"ok": True, **result})
        except Exception as e:
            return self._send(500, {"error": "get_cases_failed", "message": str(e)})

    def _handle_enforcement_get_case_detail(self, qs: dict) -> None:
        """GET /api/enforcement/case-detail — 获取案卷详情"""
        platform, err = self._get_platform(qs.get("token", ""))
        if err:
            return self._send(400, err)
        xh = qs.get("xh", "")
        lcdybh = qs.get("lcdybh", "")
        if not xh or not lcdybh:
            return self._send(400, {"error": "missing xh or lcdybh"})

        try:
            result = platform.get_case_detail(xh, lcdybh)
            return self._send(200, {"ok": True, **result})
        except Exception as e:
            return self._send(500, {"error": "get_detail_failed", "message": str(e)})

    def _handle_enforcement_get_documents(self, qs: dict) -> None:
        """GET /api/enforcement/documents — 获取文书列表"""
        platform, err = self._get_platform(qs.get("token", ""))
        if err:
            return self._send(400, err)

        try:
            page = int(qs.get("page", 1))
            rows = int(qs.get("rows", 20))
            result = platform.get_documents(page=page, rows=rows)
            return self._send(200, {"ok": True, **result})
        except Exception as e:
            return self._send(500, {"error": "get_documents_failed", "message": str(e)})

    def _handle_enforcement_document_download(self, qs: dict) -> None:
        """GET /api/enforcement/document-download — 下载单份文书"""
        platform, err = self._get_platform(qs.get("token", ""))
        if err:
            return self._send(400, err)
        file_id = qs.get("fileId", "")
        if not file_id:
            return self._send(400, {"error": "missing fileId"})

        try:
            save_dir = _sanitize_output_path(qs.get("saveDir", "/tmp/eco-aegis-docs"))
            path = platform.download_document(file_id, save_dir)
            return self._send(200, {"ok": True, "fileId": file_id, "path": path})
        except Exception as e:
            return self._send(500, {"error": "download_failed", "message": str(e)})

    def _handle_enforcement_get_enterprises(self, qs: dict) -> None:
        """GET /api/enforcement/enterprises — 获取企业列表"""
        platform, err = self._get_platform(qs.get("token", ""))
        if err:
            return self._send(400, err)

        try:
            page = int(qs.get("page", 1))
            rows = int(qs.get("rows", 20))
            result = platform.get_enterprises(page=page, rows=rows)
            return self._send(200, {"ok": True, **result})
        except Exception as e:
            return self._send(500, {"error": "get_enterprises_failed", "message": str(e)})


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def main() -> None:
    print(f"[eco-bridge] 启动 :{PORT}")
    print(f"[eco-bridge] 模式: {'真实 Hermes' if os.getenv('HERMES_REAL') == '1' else '占位模拟'}")
    print(f"[eco-bridge] HERMES_REAL={os.getenv('HERMES_REAL')}")
    print(f"[eco-bridge] Hermes Python: {_find_hermes_python()}")
    print(f"[eco-bridge] 端点:")
    print(f"  POST /api/platform/match   — 平台地址匹配")
    print(f"  POST /api/platform/captcha — 验证码抓取")
    print(f"  POST /api/platform/login   — 登录接管")
    print(f"  POST /api/platform/add     — 新增平台（持久化）")
    print(f"  POST /api/platform/delete  — 删除平台")
    print(f"  POST /api/office/open      — 打开文书")
    print(f"  POST /api/office/ai-review — 触发 AI 审阅")
    print(f"  POST /api/office/sync      — 协同编辑同步")
    print(f"  GET  /api/auth/health      — 认证健康检测")
    print(f"  GET  /api/office/state     — 文书状态查询")
    print(f"  GET  /api/office/review-stats — 评查看板")
    print(f"  GET  /api/hermes/memory    — Hermes 记忆")
    print(f"  GET  /api/gis/latest       — GIS 操作记录")
    print(f"  GET  /api/proxy?url=       — 反向代理（绕过 X-Frame-Options）")
    print(f"")
    print(f"  ── 执法办案 Skill ──")
    print(f"  POST /api/enforcement/connect    — 连接平台（Chrome复用/登录）")
    print(f"  POST /api/enforcement/scan       — 扫描平台模块")
    print(f"  POST /api/enforcement/sync       — 全量同步数据")
    print(f"  POST /api/enforcement/export     — 导出 Excel")
    print(f"  POST /api/enforcement/inspect    — 日常巡检")
    print(f"  GET  /api/enforcement/cases?token= — 获取案卷列表")
    print(f"  GET  /api/enforcement/documents?token= — 获取文书列表")
    print(f"  GET  /api/enforcement/document-download?token=&fileId= — 下载文书")
    print(f"  GET  /api/enforcement/enterprises?token= — 获取企业列表")
    srv = ThreadingHTTPServer((BIND_ADDR, PORT), Handler)
    srv.serve_forever()


if __name__ == "__main__":
    main()
