#!/usr/bin/env python3
"""Feishu Bot auto-replier - reads events from consumer, replies via API"""
import os, sys, json, time, importlib, requests, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8-sig', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8-sig', errors='replace')
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "gateway" / "feishu_events"
CACHE = EVENTS / ".done"

AP_ID, AP_KEY = "cli_aae3f90345385be0", "g9xr95QkZTAgscShUa7b6e6nHbzevSGM"
_token, _exp = None, 0

def gt():
    global _token, _exp
    if _token and time.time() < _exp - 60: return _token
    r = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                     json={"app_id":AP_ID,"app_secret":AP_KEY}, timeout=10).json()
    if r.get("code") == 0:
        _token, _exp = r["tenant_access_token"], time.time() + r.get("expire",7200)
        return _token

def reply(mid, txt):
    t = gt()
    if not t: return
    hd = {"Authorization":f"Bearer {t}","Content-Type":"application/json"}
    bd = {"content":json.dumps({"text":txt},ensure_ascii=False),"msg_type":"text"}
    requests.post(f"https://open.feishu.cn/open-apis/im/v1/messages/{mid}/reply", headers=hd, json=bd, timeout=15)

DONE = set()
if CACHE.exists():
    DONE = set(filter(None, CACHE.read_text("utf-8", errors="replace").strip().split("\n")))

def ask(msg):
    m = msg.strip().lower()
    if m in ("niha","hi","hello","zaima"):
        return "Welcome! I am ECO AGENT. Send law name for search, or describe violation for penalty advice."
    if m in ("help","?","h") or "bangzhu" in m:
        return "Commands:\n- send law name (e.g. dqwrffz)\n- describe violation facts\n- case + keyword\n- status"
    if m in ("status",):
        return "ECO AGENT running | events: online | knowledge base: ready"
    try:
        spec = importlib.util.spec_from_file_location("m", str(ROOT/"_scripts"/"eco-knowledge-mcp.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        v = mod.find_vault_path()
        if v and v.exists():
            res = mod.search_in_files(mod.collect_wiki_files(v), msg, 3)
            if res:
                out = [f"Results for '{msg[:20]}':"]
                for r in res:
                    out.append(f"\n- {r['title']}")
                    s = r.get("snippet","")[:120]
                    if s: out.append(f"  {s}")
                return "".join(out)
    except Exception as e:
        print(f"[MCP] {e}")
    return f"Got: '{msg[:50]}'. Send 'help' for instructions."

print("[S] Replier started", flush=True)
while True:
    try:
        for f in sorted(EVENTS.glob("*.json")):
            if f.name.startswith("."): continue
            try:
                d = json.loads(f.read_text("utf-8", errors="replace"))
                mid = d.get("message_id","")
                content = d.get("content","").strip()
                if mid and content and mid not in DONE:
                    DONE.add(mid)
                    CACHE.write_text("\n".join(sorted(DONE)))
                    txt = ask(content)
                    reply(mid, txt)
                    print(f"[OK] {content[:20]} -> {txt[:20]}", flush=True)
                f.unlink(missing_ok=True)
            except Exception as e:
                print(f"[E] {f.name}: {e}", flush=True)
                try: f.unlink(missing_ok=True)
                except: pass
    except Exception as e:
        print(f"[L] {e}", flush=True)
    time.sleep(2)
