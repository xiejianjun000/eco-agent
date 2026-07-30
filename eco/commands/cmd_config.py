"""
eco config - Configuration management (~/.eco/.env)
"""
import os, logging
from pathlib import Path
log = logging.getLogger("eco.config")
logging.basicConfig(level=logging.INFO, format="%(message)s")
CFG = Path.home() / ".eco"
ENV = CFG / ".env"

def run(args):
    match args.action:
        case "show": return _show()
        case "get": return _get(args.key)
        case "set": return _set(args.key, args.value)
        case "init": return _init()
        case "path":
            print(f"Config dir: {CFG}")
            print(f"Env file: {ENV}")
            return 0
        case _: return 1

def _show():
    print(f"Config dir: {CFG}\n")
    if ENV.exists():
        print("--- .env ---")
        for line in ENV.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                if any(s in k.upper() for s in ["KEY", "SECRET", "TOKEN"]):
                    v = (v[:4] + "****") if v else ""
                print(f"  {k}={v}")
    else:
        print("(.env not found, run eco setup)")
    return 0

def _get(key):
    if not key:
        log.error("Specify config key")
        return 1
    val = os.environ.get(key) or _env_get(key)
    if val:
        print(val)
        return 0
    log.info(f"{key} not set")
    return 1

def _set(key, value):
    if not key or value is None:
        log.error("Usage: eco config set <key> <value>")
        return 1
    CFG.mkdir(parents=True, exist_ok=True)
    env = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env[key] = value
    ENV.write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    log.info(f"Set {key}")
    return 0

def _init():
    CFG.mkdir(parents=True, exist_ok=True)
    if not ENV.exists():
        ENV.write_text("# ECO AGENT config\n")
    (CFG / "profiles").mkdir(exist_ok=True)
    log.info(f"Config initialized: {CFG}")
    return 0

def _env_get(key):
    if not ENV.exists():
        return None
    for line in ENV.read_text().splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()
    return None
