#!/usr/bin/env python3
"""轻量会话探针 — 用持久化 cookie 探测会话是否存活，无需浏览器"""
import json, sys, os, subprocess
from datetime import datetime, timezone

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")
ALERTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "alerts")

def load_platform_config(platform_id):
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "platforms.config.json")
    with open(cfg_path) as f:
        cfg = json.load(f)
    return cfg.get(platform_id)

def load_state(platform_id):
    path = os.path.join(STATE_DIR, f"{platform_id}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {
        "platform": platform_id,
        "lastSessionOkAt": None,
        "lastCredentialAuthAt": None,
        "consecutiveFailures": 0,
        "circuitState": "closed",
        "lastError": None,
        "history": []
    }

def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    path = os.path.join(STATE_DIR, f"{state['platform']}.json")
    with open(path, "w") as f:
        json.dump(state, f, indent=2, default=str)

def probe_session_http(platform_id, storage_state_path):
    """
    用 requests 带本地 cookie 探针平台业务接口
    判定：200 且含 probeMarker（不跳转登录页）= 会话有效
    注意：这依赖于 storageState.json 中的 cookie
    """
    cfg = load_platform_config(platform_id)
    if not cfg:
        return {"status": "error", "reason": f"unknown platform: {platform_id}"}

    # 加载 cookie
    cookies = {}
    if os.path.exists(storage_state_path):
        with open(storage_state_path) as f:
            ss = json.load(f)
        for c in ss.get("cookies", []):
            cookies[c["name"]] = c["value"]

    if not cookies:
        return {"status": "no_cookies", "reason": "storageState not found or empty"}

    try:
        import requests
        resp = requests.get(
            cfg["probeUrl"],
            cookies=cookies,
            timeout=15,
            allow_redirects=False,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/131.0.0.0"}
        )

        # 检查是否跳转到登录页
        if resp.status_code in (301, 302):
            location = resp.headers.get("Location", "")
            if "login" in location.lower() or "cas" in location.lower():
                return {"status": "session_dead", "reason": f"redirected to login: {location[:80]}"}

        # 检查响应体是否有业务标识
        probe_marker = cfg.get("probeMarker")
        if probe_marker and probe_marker not in resp.text:
            return {"status": "session_dead", "reason": f"probeMarker '{probe_marker}' not found"}

        return {"status": "session_alive", "httpStatus": resp.status_code, "latencyMs": resp.elapsed.total_seconds() * 1000}

    except ImportError:
        return {"status": "skipped", "reason": "requests not installed"}
    except Exception as e:
        return {"status": "network_error", "reason": str(e)[:200]}

def write_alert(platform_id, title, body, severity="CRITICAL"):
    os.makedirs(ALERTS_DIR, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filename = f"alert_{platform_id}_{ts.replace(':', '-')}.json"
    alert = {
        "platform": platform_id,
        "title": title,
        "body": body,
        "severity": severity,
        "timestamp": ts
    }
    with open(os.path.join(ALERTS_DIR, filename), "w") as f:
        json.dump(alert, f, indent=2)
    return filename

def main():
    if len(sys.argv) < 2:
        print("Usage: probe_session.py <platform_id> [storage_state_path]")
        sys.exit(1)

    platform_id = sys.argv[1]
    storage_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(STATE_DIR, f"{platform_id}.storageState.json")

    state = load_state(platform_id)
    cfg = load_platform_config(platform_id)

    now = datetime.now(timezone.utc).isoformat()
    entry = {"time": now, "type": "session_probe"}

    result = probe_session_http(platform_id, storage_path)
    entry["result"] = result

    if result["status"] == "session_alive":
        state["lastSessionOkAt"] = now
        state["consecutiveFailures"] = 0
        print(f"[OK] {cfg['name']}: 会话存活")
    elif result["status"] == "session_dead":
        state["consecutiveFailures"] += 1
        state["lastError"] = result.get("reason", "")
        print(f"[DEAD] {cfg['name']}: 会话失效 ({result.get('reason', '')})")
        # 会话过期是日常，不到告警级别
    elif result["status"] == "network_error":
        state["lastError"] = result.get("reason", "")
        print(f"[UNREACHABLE] {cfg['name']}: {result.get('reason', '')}")
        # 不统计为凭据失败
    else:
        print(f"[SKIP] {cfg['name']}: {result.get('reason', '')}")

    state["history"].append(entry)
    # 只保留最近 30 条
    state["history"] = state["history"][-30:]

    # 凭据验证过期检查（7天未验证 → 降级标注）
    last_auth = state.get("lastCredentialAuthAt")
    if last_auth:
        try:
            last_auth_dt = datetime.fromisoformat(last_auth)
            days_since = (datetime.now(timezone.utc) - last_auth_dt).days
            if days_since > 7:
                print(f"[WARN] {cfg['name']}: 距上次凭据验证已 {days_since} 天，建议人工确认")
                write_alert(platform_id,
                    f"{cfg['name']} 凭据长期未验证",
                    f"距上次凭据级验证已 {days_since} 天，虽然会话可能仍有效，但无法确认凭证本身未被修改。",
                    "WARNING")
        except Exception:
            pass

    save_state(state)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
