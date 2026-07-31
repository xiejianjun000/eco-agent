"""
eco mcp - MCP protocol server (GovMCP integration)
"""
import sys
import logging
log = logging.getLogger("eco.mcp")
logging.basicConfig(level=logging.INFO, format="%(message)s")

def run(args):
    t = getattr(args, "transport", None) or ("http" if args.http else "stdio")
    port = args.port
    try:
        if t == "stdio": return _serve_stdio()
        elif t in ("http", "sse"): return _serve_http(port)
        elif t in ("websocket", "ws"): return _serve_ws(port)
    except KeyboardInterrupt:
        log.info("\nMCP server stopped")
        return 0
    except Exception as e:
        log.error(f"Failed: {e}")
        return 1
    return 1

def _ensure_govmcp():
    import importlib.util
    if importlib.util.find_spec("govmcp") is None:
        log.error("GovMCP not installed. Run: pip install govmcp")
        sys.exit(1)

def _serve_stdio():
    _ensure_govmcp()
    from govmcp.protocol.server import GovMCPServer
    import asyncio
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
