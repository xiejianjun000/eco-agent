#!/usr/bin/env python3
"""eco CLI - Main dispatcher"""
import argparse, sys

def _build_parser():
    parser = argparse.ArgumentParser(
        prog="eco",
        description="ECO AGENT - Five-layer loop autonomous AI agent system",
    )
    parser.add_argument("--version", "-V", action="version", version="eco 5.0.0a1")
    sub = parser.add_subparsers(dest="command")

    # chat
    p = sub.add_parser("chat", help="Talk to ECO AGENT")
    p.add_argument("query", nargs="?", default=None)
    p.add_argument("--model", default=None)
    p.add_argument("--provider", default=None)

    # gateway
    p = sub.add_parser("gateway", help="Manage message gateway")
    p.add_argument("action", choices=["start","stop","restart","status"])
    p.add_argument("--port", type=int, default=7070)
    p.add_argument("--daemon", action="store_true")

    # mcp
    p = sub.add_parser("mcp", help="MCP protocol server")
    p.add_argument("action", choices=["serve"], nargs="?", default="serve")
    p.add_argument("--http", action="store_true")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--transport", choices=["stdio","sse","websocket"], default=None)

    # serve (P2)
    p = sub.add_parser("serve", help="OpenAI-compatible API server")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--api-key", default=None)

    # setup
    p = sub.add_parser("setup", help="Interactive setup wizard")
    p.add_argument("--quick", action="store_true")

    # skills
    p = sub.add_parser("skills", help="Manage skills")
    p.add_argument("action", choices=["list","install","remove","info"])
    p.add_argument("name", nargs="?", default=None)

    # config
    p = sub.add_parser("config", help="Configuration management")
    p.add_argument("action", choices=["show","get","set","init","path"])
    p.add_argument("key", nargs="?", default=None)
    p.add_argument("value", nargs="?", default=None)

    # doctor
    p = sub.add_parser("doctor", help="System health check")
    p.add_argument("--fix", action="store_true")
    p.add_argument("--verbose", "-v", action="store_true")

    # evolution
    p = sub.add_parser("evolution", help="Trigger evolution loop")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--report", action="store_true")

    # version
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

    module_map = {
        "chat": "cmd_chat", "gateway": "cmd_gateway", "mcp": "cmd_mcp",
        "serve": "cmd_serve", "setup": "cmd_setup", "skills": "cmd_skills",
        "config": "cmd_config", "doctor": "cmd_doctor", "evolution": "cmd_evolution",
    }
    mod = __import__(f"eco.commands.{module_map[args.command]}", fromlist=["run"])
    return mod.run(args)

if __name__ == "__main__":
    sys.exit(main())
