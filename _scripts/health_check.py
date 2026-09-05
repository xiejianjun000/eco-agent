#!/usr/bin/env python3
"""
_scripts/health_check.py — eco-agent 一键健康自检

把"能力挂了但凭证没挂 / 注册了但没接线 / 挂了但用不了"三类隐性缺口
变成一张显性体检表。输出 ✅/⚠️/❌ + 底部"待办清单"。

用法:
  python3 _scripts/health_check.py           # 本地体检（不联网）
  python3 _scripts/health_check.py --live    # 附加连通性探测（平台可达/鉴权）
  python3 _scripts/health_check.py --json    # JSON 输出（脚本消费）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OK, WARN, FAIL = "✅", "⚠️", "❌"


def _mark(ok: bool, warn: bool = False) -> str:
    if ok:
        return OK
    return WARN if warn else FAIL


def check() -> dict:
    rows: list[dict] = []
    todos: list[str] = []

    # ── 1. 凭证缺口（复用统一配置脚本） ──
    try:
        from _scripts.setup_credentials import check as cred_check

        cred = cred_check(ROOT / ".env")
        rows.append(
            {
                "group": "凭证配置",
                "name": cred["summary"],
                "ok": not cred["missing"],
                "detail": "; ".join(cred["missing"]) if cred["missing"] else "全部就绪",
            }
        )
        if cred["missing"]:
            todos.append(f"补凭证: {'、'.join(cred['missing'])}（跑 python3 _scripts/setup_credentials.py）")
    except Exception as e:  # noqa: BLE001
        rows.append({"group": "凭证配置", "name": "检查失败", "ok": False, "detail": str(e)})

    # ── 2. govmcp 工具注册表 ──
    try:
        from govmcp_tools import register_all, registry

        if registry.count() == 0:
            register_all()
        cats: dict[str, int] = {}
        for name, tool in registry.tools.items():
            meta = getattr(tool.handler, "_govmcp_meta", {})
            cat = meta.get("category", "未分类")
            cats[cat] = cats.get(cat, 0) + 1
        platforms = "、".join(f"{c}({n})" for c, n in cats.items() if c.startswith("执法平台"))
        rows.append(
            {
                "group": "工具注册",
                "name": f"govmcp 工具 {registry.count()} 个",
                "ok": registry.count() >= 100,
                "detail": "三平台: " + platforms,
            }
        )
    except Exception as e:  # noqa: BLE001
        rows.append({"group": "工具注册", "name": "govmcp 注册表", "ok": False, "detail": str(e)})

    # ── 3. 聊天通道接线 ──
    try:
        from agent_core.wiring_manifest import WIRED_REQUIRED
        from server.api.chat import _codex_tools

        chat_names = {t["function"]["name"] for t in _codex_tools()}
        missing = [n for n in WIRED_REQUIRED if n not in chat_names]
        rows.append(
            {
                "group": "聊天接线",
                "name": f"聊天工具 {len(chat_names)} 个（接线清单 {len(WIRED_REQUIRED)}）",
                "ok": not missing,
                "detail": f"缺口: {missing}" if missing else "接线清单与聊天表一致",
            }
        )
        if missing:
            todos.append(f"接线缺口: {missing}")
    except Exception as e:  # noqa: BLE001
        rows.append({"group": "聊天接线", "name": "检查失败", "ok": False, "detail": str(e)})

    # ── 4. 权限覆盖 ──
    try:
        from agent_core.permissions import load_overrides

        ov = load_overrides()
        rows.append(
            {
                "group": "权限闸门",
                "name": f"PERMISSION.md 覆盖 {len(ov)} 项",
                "ok": len(ov) >= 20,
                "detail": "已加载" if ov else "未加载",
            }
        )
    except Exception as e:  # noqa: BLE001
        rows.append({"group": "权限闸门", "name": "检查失败", "ok": False, "detail": str(e)})

    # ── 5. Web 构建产物 ──
    web_ok = (ROOT / "web" / "dist" / "index.html").exists()
    rows.append(
        {
            "group": "Web UI",
            "name": "前端构建产物",
            "ok": web_ok,
            "detail": "dist 已构建" if web_ok else "未构建（cd web && npm run build）",
        }
    )
    if not web_ok:
        todos.append("构建前端: cd web && npm run build")

    # ── 6. 提示词组装 ──
    try:
        from agent_core.prompt_engine import get_prompt_engine

        eng = get_prompt_engine()
        n = len(eng.list_sections())
        rows.append(
            {
                "group": "提示词组装",
                "name": f"基础片段 {n} 个 + 注入 {len(eng.list_injections())} 条",
                "ok": n >= 4,
                "detail": f"当前阶段: {eng.phase}",
            }
        )
    except Exception as e:  # noqa: BLE001
        rows.append({"group": "提示词组装", "name": "检查失败", "ok": False, "detail": str(e)})

    # ── 7. 服务器状态 ──
    try:
        import urllib.request

        with urllib.request.urlopen("http://127.0.0.1:8321/healthz", timeout=3) as r:
            j = json.loads(r.read())
        rows.append(
            {
                "group": "服务器",
                "name": "eco-server 8321",
                "ok": True,
                "detail": f"status={j.get('status')} version={j.get('version')}",
            }
        )
    except Exception:
        rows.append(
            {
                "group": "服务器",
                "name": "eco-server 8321",
                "ok": False,
                "detail": "未运行（python3 -m eco.cli server --port 8321）",
            }
        )
        todos.append("启动服务器: python3 -m eco.cli server --port 8321")

    # ── 8. MCP 配置清单（B 维度接线可见性）──
    try:
        line = [
            ln for ln in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if ln.strip().startswith("ECO_MCP_SERVERS=")
        ]
        servers = json.loads(line[0].split("=", 1)[1].strip()) if line else []
        rows.append(
            {
                "group": "MCP 接线",
                "name": f"已配置 {len(servers)} 个 MCP",
                "ok": len(servers) >= 3,
                "detail": "、".join(s.get("name", "?") for s in servers),
            }
        )
    except Exception as e:  # noqa: BLE001
        rows.append({"group": "MCP 接线", "name": "配置解析失败", "ok": False, "detail": str(e)})

    # ── 9. SM3 审计链完整性（D 维度溯源自检）──
    try:
        from agent_core.prompt_engine import PromptAuditChain

        chain = PromptAuditChain()
        report = chain.verify_chain()
        ok = report.get("valid", True)
        n = report.get("entries", report.get("total", 0))
        rows.append({"group": "审计链", "name": f"SM3 审计链 {n} 条", "ok": ok, "detail": "完整可验证" if ok else "链损坏"})
        if not ok:
            todos.append("SM3 审计链校验失败——检查 ECO_DIR/prompt_audit.jsonl")
    except Exception as e:  # noqa: BLE001
        rows.append({"group": "审计链", "name": "检查失败", "ok": False, "detail": str(e)})

    # ── 8. 目录口径（工作区 vs 状态目录，防止"路径漂移"误判）──
    ws = os.environ.get("ECO_WORKSPACE_DIR", "").strip()
    ecod = os.environ.get("ECO_DIR", "").strip()
    if ws and ecod and ws != ecod:
        rows.append(
            {
                "group": "目录口径",
                "name": "工作区目录 ≠ 状态目录",
                "ok": True,
                "detail": f"工作区(产物): {ws} | 状态(审计/会话): {ecod}——两者用途不同属正常，但运行时上下文需同时标注避免误判",
            }
        )
    else:
        rows.append({"group": "目录口径", "name": "目录口径", "ok": True, "detail": f"统一目录: {ws or ecod or '默认 ~/.eco'}"})

    # ── 8. 平台连通性（仅 --live）──
    return {"rows": rows, "todos": todos, "summary": f"{sum(1 for r in rows if r['ok'])}/{len(rows)} 项通过"}


def live_probes() -> list[dict]:
    # C 维度契约基线：关键 MCP/平台端点若配置了凭证，401 即"凭证失效待换"而非普通异常
    import json as _json
    import urllib.error
    import urllib.request

    servers = []
    try:
        line = [
            ln for ln in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if ln.strip().startswith("ECO_MCP_SERVERS=")
        ]
        if line:
            servers = _json.loads(line[0].split("=", 1)[1].strip())
    except Exception:
        pass

    probes = [
        ("在线监测平台", "http://218.77.102.213:12369/wryzxjc/"),
        ("国家四平台 CAS", "https://sthjzf.lem.org.cn:8090/"),
        ("行政处罚系统", "https://eap.lem.org.cn"),
        ("水环境平台", "https://jkzx.envsc.cn"),
        ("腾讯文档 MCP 端点", "https://docs.qq.com/openapi/mcp"),
    ]
    # 腾讯文档端点：带配置的 Token 探测 → 401=凭证失效，200/405=链路通
    td = next((s for s in servers if isinstance(s, dict) and s.get("name") == "tencent_docs"), {})
    td_token = (td.get("headers") or {}).get("Authorization", "")
    rows = []
    for name, url in probes:
        try:
            headers = {}
            if name == "腾讯文档 MCP 端点" and td_token and "PASTE" not in td_token:
                headers = {"Authorization": td_token}
            req = urllib.request.Request(url, method="GET", headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                rows.append({"group": "连通性", "name": name, "ok": True, "detail": f"HTTP {r.status}"})
        except urllib.error.HTTPError as e:
            if name == "腾讯文档 MCP 端点" and e.code == 401:
                rows.append(
                    {
                        "group": "连通性",
                        "name": name,
                        "ok": False,
                        "detail": "HTTP 401 — Token 失效，重新获取后跑 setup_credentials.py 第 5 项",
                    }
                )
            else:
                rows.append(
                    {
                        "group": "连通性",
                        "name": name,
                        "ok": e.code in (401, 403),
                        "detail": f"HTTP {e.code}（{'端点可达待鉴权' if e.code in (401, 403) else '异常'}）",
                    }
                )
        except Exception as e:  # noqa: BLE001
            rows.append({"group": "连通性", "name": name, "ok": False, "detail": str(e)[:80]})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="eco-agent 一键健康自检")
    ap.add_argument("--live", action="store_true", help="附加平台连通性探测")
    ap.add_argument("--json", action="store_true", help="JSON 输出")
    args = ap.parse_args()

    result = check()
    if args.live:
        result["rows"].extend(live_probes())
        result["summary"] = f"{sum(1 for r in result['rows'] if r['ok'])}/{len(result['rows'])} 项通过"

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=1))
        return

    print("\n════════ eco-agent 健康自检 ════════")
    cur = None
    for r in result["rows"]:
        if r["group"] != cur:
            cur = r["group"]
            print(f"\n【{cur}】")
        print(f"  {_mark(r['ok'])} {r['name']}" + (f" — {r['detail']}" if r.get("detail") else ""))
    print(f"\n── 总评: {result['summary']} ──")
    if result["todos"]:
        print("\n【待办清单】")
        for t in result["todos"]:
            print(f"  · {t}")
    else:
        print("无待办，全量就绪。")
    print()


if __name__ == "__main__":
    main()
