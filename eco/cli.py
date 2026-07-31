#!/usr/bin/env python3
"""eco CLI - Main dispatcher"""
import argparse
import sys

def _build_parser():
    parser = argparse.ArgumentParser(prog="eco", description="ECO AGENT")
    parser.add_argument("--version", "-V", action="version", version="eco 5.0.0a1")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("chat", help="Talk to ECO AGENT")
    p.add_argument("query", nargs="?", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--provider", default=None)
    p.add_argument("--verbose", "-v", action="store_true",
                   help="轨迹模式：显示思考/工具调用/结果与 swarm 阶段耗时（写入 SM3 审计链 source=trace）")
    p.add_argument("--continue", "-c", dest="continue_session", action="store_true",
                   help="恢复最近活跃工作区的会话历史继续对话")
    p.add_argument("--resume", "-r", dest="resume", default=None, metavar="SLUG",
                   help="按工作区名/slug 恢复指定会话历史")

    p = sub.add_parser("gateway", help="Manage gateway")
    p.add_argument("action", choices=["start","stop","restart","status","channels"])
    p.add_argument("channel_args", nargs="*", default=[],
                   help="channels 子命令参数，如: eco gateway channels list")
    p.add_argument("--port", type=int, default=7070)
    p.add_argument("--daemon", action="store_true")

    p = sub.add_parser("mcp", help="MCP protocol server")
    p.add_argument("action", choices=["serve"], nargs="?", default="serve")
    p.add_argument("--http", action="store_true")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--transport", choices=["stdio","sse","websocket"], default=None)

    p = sub.add_parser("serve", help="OpenAI-compatible API")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--api-key", default=None)

    p = sub.add_parser("setup", help="Setup wizard")
    p.add_argument("--quick", action="store_true")
    p = sub.add_parser("skills", help="Manage skills")
    p.add_argument("action", choices=["list","install","remove","info","versions","rollback"])
    p.add_argument("name", nargs="?", default=None)
    p = sub.add_parser("config", help="Config")
    p.add_argument("action", choices=["show","get","set","init","path","model"])
    p.add_argument("key", nargs="?", default=None)
    p.add_argument("value", nargs="?", default=None)
    p = sub.add_parser("corrections", help="Manage user corrections")
    p.add_argument("action", choices=["list","remove","clear"])
    p.add_argument("value", nargs="?", default=None)
    p = sub.add_parser("workspace", help="Project workspaces (B1)")
    p.add_argument("action", choices=["create","list","open","close","show","freeze"])
    p.add_argument("name", nargs="?", default=None)
    p = sub.add_parser("doctor", help="Health check")
    p.add_argument("--fix", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")
    p = sub.add_parser("evolution", help="Evolution")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--report", action="store_true")
    p = sub.add_parser("trace", help="Span tree traces (observability)")
    p.add_argument("session", nargs="?", default=None, help="会话 ID（缺省列出全部）")
    p.add_argument("--tree", action="store_true", help="树形展示 span 树")
    p.add_argument("--otel", nargs="?", const="", default=None, metavar="OUT.json",
                   help="导出 OTLP JSON（缺省写到 ./<session>.otlp.json）")
    p.add_argument("--export", choices=["otlp"], default=None,
                   help="直接 POST 到 OTel collector（失败降级写本地文件）")
    p.add_argument("--endpoint", default=None, metavar="URL",
                   help="OTel collector endpoint（默认 http://localhost:4318）")
    p = sub.add_parser("auth", help="Non-interactive L4 auth grants")
    p.add_argument("auth_action", choices=["grant", "revoke", "list"], nargs="?", default="list")
    p.add_argument("grant_id", nargs="?", default=None)
    p.add_argument("--level", default="L4", choices=["L3", "L4"])
    p.add_argument("--ttl", type=int, default=3600, help="授权有效期（秒）")
    p.add_argument("--scope", default="*", help="授权范围：工具名或 *")
    sub.add_parser("version", help="Show version")
    return parser

def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "version":
        from eco import __version__
        print(f"ECO AGENT v{__version__}")
        return 0
    mod = __import__(f"eco.commands.cmd_{args.command}", fromlist=["run"])
    return mod.run(args)

if __name__ == "__main__":
    sys.exit(main())
