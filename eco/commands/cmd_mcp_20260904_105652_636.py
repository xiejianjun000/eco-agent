"""
eco mcp - MCP protocol server (GovMCP integration) + 管理面（P0-3）

对标 Hermes MCP Command Center：
  eco mcp serve [--http] [--port P] [--transport stdio|sse|websocket]   # GovMCP server
  eco mcp add <name> --transport sse|http --url <URL>                    # 导入 MCP server
  eco mcp add <name> --transport stdio --cmd '["python","x.py"]'         # stdio 导入
  eco mcp list                                                            # 清单 + 健康摘要
  eco mcp health [<name>]                                                 # 真实连接健康检查
  eco mcp usage [<name>]                                                  # 用量
  eco mcp remove <name>
"""

import json
import logging
import sys

log = logging.getLogger("eco.mcp")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def build_parser(sub) -> None:
    p = sub.add_parser("mcp", help="MCP server / 管理面（对标 MCP Command Center）")
    subp = p.add_subparsers(dest="mcp_action", required=True)

    ps = subp.add_parser("serve", help="运行 GovMCP protocol server")
    ps.add_argument("--http", action="store_true")
    ps.add_argument("--port", type=int, default=8000)
    ps.add_argument("--transport", choices=["stdio", "sse", "websocket"], default=None)

    pa = subp.add_parser("add", help="导入 MCP server 配置")
    pa.add_argument("name")
    pa.add_argument("--transport", choices=["sse", "http", "stdio"], default="http")
    pa.add_argument("--url", default=None, help="sse/http 目标 URL")
    pa.add_argument(
        "--cmd", dest="mcp_cmd", default=None, help='stdio 启动命令：JSON 数组（如 \'["python","run.py"]\'）或单条命令'
    )

    subp.add_parser("list", help="列出已导入 server（含健康摘要）")

    ph = subp.add_parser("health", help="真实连接健康检查（list_tools 验证）")
    ph.add_argument("name", nargs="?", default=None)

    pu = subp.add_parser("usage", help="调用用量统计")
    pu.add_argument("name", nargs="?", default=None)

    pr = subp.add_parser("remove", help="移除 server 配置")
    pr.add_argument("name")


def run(args) -> int:
    action = getattr(args, "mcp_action", None)
    if action is None:
        print("eco mcp: need action (serve/add/list/health/usage/remove)")
        return 2
    if action == "serve":
        t = getattr(args, "transport", None) or ("http" if args.http else "stdio")
        port = args.port
        try:
            if t == "stdio":
                return _serve_stdio()
            elif t in ("http", "sse"):
                return _serve_http(port)
            elif t == "websocket":
                return _serve_ws(port)
        except KeyboardInterrupt:
            log.info("\nMCP server stopped")
            return 0
        except Exception as e:
            log.error(f"Failed: {e}")
            return 1
        return 1
    return _run_manage(action, args)


def _run_manage(action, args) -> int:
    from pathlib import Path

    ROOT = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(ROOT))
    from agent_core.mcp_registry import MCPRegistry

    reg = MCPRegistry()
    name = getattr(args, "name", None)
    try:
        if action == "add":
            transport = getattr(args, "transport", None) or "http"
            cmd_raw = getattr(args, "mcp_cmd", None)
            command = None
            if cmd_raw:
                try:
                    command = json.loads(cmd_raw)
                except json.JSONDecodeError:
                    command = cmd_raw.split()
            entry = reg.add(args.name, transport, url=getattr(args, "url", None), command=command)
            c = entry["config"]
            print(f"mcp server {args.name} added  transport={c.get('transport')} url={c.get('url') or c.get('command')}")
        elif action == "list":
            rows = reg.list()
            if not rows:
                print("(registry empty) — eco mcp add <name> --transport sse --url <URL>")
            for r in rows:
                ok = r["ok"]
                mark = "OK" if ok else ("FAIL" if ok is False else "--")
                print(
                    f"{r['name']:<16} {r['transport']:<6} {r['url'][:40]:<40} "
                    f"{mark:<4} tools={r['tools']:<3} calls={r['call_count']}"
                )
        elif action == "remove":
            ok = reg.remove(name) if name else False
            print(f"removed {name}" if ok else f"not found: {name}")
        elif action == "health":
            res = reg.health(name)
            for n, r in res["results"].items():
                mark = "OK" if r["ok"] else "FAIL"
                detail = r.get("detail") or ""
                print(f"{mark} {n:<16} tools={r.get('tool_count', 0):<3} latency={r.get('latency_ms')}ms {detail}")
                if r.get("tool_names"):
                    print(f"    tools: {', '.join(r['tool_names'][:8])}")
        elif action == "usage":
            u = reg.usage(name)
            if name:
                print(f"{name}: {u.get('usage', {})}")
            else:
                for n, s in u.get("servers", {}).items():
                    print(f"{n:<16} calls={s.get('call_count', 0):<5} last={s.get('last_used_at') or '-'}")
                    bt = s.get("by_tool") or {}
                    if bt:
                        top = sorted(bt.items(), key=lambda kv: -kv[1])[:5]
                        print("    top: " + ", ".join(f"{t}x{c}" for t, c in top))
    except (ValueError, KeyError) as e:
        log.error(f"error: {e}")
        return 1
    return 0


def _ensure_govmcp():
    import importlib.util

    if importlib.util.find_spec("govmcp") is None:
        log.error("GovMCP not installed. Run: pip install govmcp")
        sys.exit(1)


def _serve_stdio():
    _ensure_govmcp()
    import asyncio

    from govmcp.protocol.server import GovMCPServer

    log.info("ECO AGENT MCP Server (stdio)")
    asyncio.run(GovMCPServer().serve_stdio_forever())
    return 0


def _serve_http(port):
    _ensure_govmcp()
    import asyncio

    log.info(f"ECO AGENT MCP Server (HTTP) :{port}")
    asyncio.run(_run_mcp_server("http", port))
    return 0


def _serve_ws(port):
    _ensure_govmcp()
    import asyncio

    log.info(f"ECO AGENT MCP Server (WebSocket) :{port}")
    asyncio.run(_run_mcp_server("ws", port))
    return 0


async def _run_mcp_server(mode, port):
    from govmcp.protocol.server import GovMCPServer

    s = GovMCPServer()
    if mode == "http":
        await s.serve_http_forever(host="0.0.0.0", port=port)
    else:
        await s.serve_websocket_forever(host="0.0.0.0", port=port)
