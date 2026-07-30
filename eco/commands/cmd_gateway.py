"""
eco gateway - Message gateway lifecycle management
"""
import sys, logging, os, signal, subprocess
from pathlib import Path
log = logging.getLogger("eco.gateway")
logging.basicConfig(level=logging.INFO, format="%(message)s")
ROOT = Path(__file__).resolve().parent.parent.parent
GW = ROOT / "gateway"

def run(args):
    match args.action:
        case "start": return _start(args.port, args.daemon)
        case "stop": return _stop()
        case "restart": _stop(); return _start(args.port, args.daemon)
        case "status": return _status()

def _start(port, daemon):
    sv = GW / "eco-gateway-server.py"
    if not sv.exists():
        log.error(f"Gateway script not found: {sv}")
        return 1
    log.info(f"Starting gateway (port {port})...")
    if daemon:
        lf = ROOT / "gateway.log"
        p = subprocess.Popen(
            [sys.executable, str(sv), "--port", str(port)],
            stdout=open(lf, "w"), stderr=subprocess.STDOUT, cwd=ROOT,
        )
        log.info(f"Gateway started PID={p.pid} log={lf}")
        return 0
    os.chdir(str(ROOT))
    os.execvp(sys.executable, [sys.executable, str(sv), "--port", str(port)])

def _stop():
    pf = ROOT / "gateway.pid"
    if not pf.exists():
        log.info("Gateway not running")
        return 0
    try:
        pid = int(pf.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        pf.unlink(missing_ok=True)
        log.info(f"Gateway stopped PID={pid}")
    except ProcessLookupError:
        pf.unlink(missing_ok=True)
        log.info("Gateway process was already gone")
    return 0

def _status():
    pf = ROOT / "gateway.pid"
    if pf.exists():
        try:
            pid = int(pf.read_text().strip())
            os.kill(pid, 0)
            log.info(f"Gateway running PID={pid}")
            return 0
        except (ProcessLookupError, OSError):
            pf.unlink(missing_ok=True)
    log.info("Gateway not running")
    return 1
