#!/usr/bin/env python3
"""eco CLI - Main dispatcher"""
import argparse, sys

def _build_parser():
    parser = argparse.ArgumentParser(prog="eco", description="ECO AGENT")
    parser.add_argument("--version", "-V", action="version", version="eco 5.0.0a1")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("chat", help="Talk to ECO AGENT")
    p.add_argument("query", nargs="?", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--provider", default=None)

    p = sub.add_parser("gateway", help="Manage gateway")
    p.add_argument("action", choices=["start","stop","restart","status"])
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
    p.add_argument("action", choices=["list","install","remove","info"])
    p.add_argument("name", nargs="?", default=None)
    p = sub.add_parser("config", help="Config")
    p.add_argument("action", choices=["show","get","set","init","path"])
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
