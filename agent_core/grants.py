#!/usr/bin/env python3
"""grants.py — 非交互 L4 授权令牌通道

场景：脚本/CI 中无法交互 y/n，L4（外部服务写）工具会被一律拒绝。
授权令牌机制：
  eco auth grant --level L4 --ttl 3600 [--scope <tool|*>]
      生成 ~/.eco/grants/<id>.json，含 expires_at、scope，
      signature = sm3(secret + canonical(body))；secret 为本机随机密钥
      ~/.eco/grant_secret（0600，自动生成）。无密钥无法伪造签名。
  eco auth revoke <id>   撤销（删除授权文件）
  eco auth list          列出有效/过期授权

权限门（permissions.gate_tool_call）在交互确认前先查有效授权：
命中则放行并以 source=grant:<id> 写 SM3 审计链。

安全边界：授权仅放行 level <= grant.level 的工具（L4 授权可覆盖 L3），
scope 限制到具体工具或 "*" 全部。不提供"跳过全部闸门"的裸开关。
"""
from __future__ import annotations

import hashlib
import json
import secrets as _secrets
import time
from datetime import datetime
from pathlib import Path

GRANTS_DIR = Path.home() / ".eco" / "grants"
SECRET_FILE = Path.home() / ".eco" / "grant_secret"

_LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3, "L4": 4}


def _sm3(text: str) -> str:
    return hashlib.new("sm3", text.encode("utf-8")).hexdigest()


def _secret(create: bool = True) -> str:
    """本机授权签名密钥（首次自动生成，0600）"""
    if SECRET_FILE.exists():
        return SECRET_FILE.read_text(encoding="utf-8").strip()
    if not create:
        return ""
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    s = _secrets.token_hex(32)
    SECRET_FILE.write_text(s, encoding="utf-8")
    try:
        SECRET_FILE.chmod(0o600)
    except OSError:
        pass
    return s


def _sign(body: dict) -> str:
    return _sm3(_secret() + "|" + json.dumps(body, ensure_ascii=False, sort_keys=True))


def _now() -> float:
    return time.time()


def grant(level: str = "L4", ttl: int = 3600, scope: str = "*",
          grants_dir: Path | None = None) -> dict:
    """生成授权令牌并落盘，返回授权 dict"""
    level = level.upper()
    if level not in _LEVEL_ORDER:
        raise ValueError(f"未知权限等级: {level}")
    gid = f"grant-{datetime.now():%Y%m%d%H%M%S}-{_secrets.token_hex(4)}"
    body = {
        "id": gid,
        "level": level,
        "scope": scope or "*",
        "issued_at": datetime.now().isoformat(timespec="seconds"),
        "expires_at": _now() + int(ttl),
        "expires_iso": datetime.fromtimestamp(_now() + int(ttl)).isoformat(timespec="seconds"),
    }
    body["signature"] = _sign(body)
    d = Path(grants_dir) if grants_dir else GRANTS_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{gid}.json").write_text(json.dumps(body, ensure_ascii=False, indent=1),
                                   encoding="utf-8")
    return body


def revoke(grant_id: str, grants_dir: Path | None = None) -> bool:
    d = Path(grants_dir) if grants_dir else GRANTS_DIR
    p = d / f"{grant_id}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def list_grants(grants_dir: Path | None = None) -> list[dict]:
    d = Path(grants_dir) if grants_dir else GRANTS_DIR
    out = []
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            try:
                g = json.loads(p.read_text(encoding="utf-8"))
                g["_expired"] = _now() > float(g.get("expires_at", 0))
                g["_valid_sig"] = _sign({k: v for k, v in g.items()
                                         if k not in ("signature", "_expired", "_valid_sig")}
                                        ) == g.get("signature")
                out.append(g)
            except (OSError, json.JSONDecodeError):
                pass
    return out


def verify(grant: dict, level: str, tool_name: str = "") -> tuple[bool, str]:
    """校验授权：签名 + 过期 + 等级覆盖 + scope。返回 (是否有效, 原因)"""
    sig = grant.get("signature", "")
    body = {k: v for k, v in grant.items() if k != "signature"}
    if _sign(body) != sig:
        return False, "签名不匹配（疑似篡改）"
    if _now() > float(grant.get("expires_at", 0)):
        return False, "授权已过期"
    if _LEVEL_ORDER.get(grant.get("level", ""), 0) < _LEVEL_ORDER.get(level, 99):
        return False, f"授权等级 {grant.get('level')} 不足以覆盖 {level}"
    scope = grant.get("scope", "*")
    if scope != "*" and tool_name and scope != tool_name:
        return False, f"授权 scope={scope} 不覆盖工具 {tool_name}"
    return True, "授权有效"


def find_valid_grant(level: str, tool_name: str = "",
                     grants_dir: Path | None = None) -> tuple[dict | None, str]:
    """在授权目录中查找可用于 (level, tool) 的有效授权"""
    d = Path(grants_dir) if grants_dir else GRANTS_DIR
    if not d.is_dir():
        return None, "无授权目录"
    last_reason = "无匹配授权"
    for p in sorted(d.glob("*.json")):
        try:
            g = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ok, reason = verify(g, level, tool_name)
        if ok:
            return g, "授权有效"
        last_reason = reason
    return None, last_reason


def audit_grant_use(grant: dict, tool_name: str, level: str):
    """授权放行写 SM3 审计链，source=grant:<id>"""
    try:
        from agent_core.prompt_engine import get_prompt_engine
        get_prompt_engine().audit.append(
            source=f"grant:{grant.get('id', '?')}",
            content=f"{tool_name} [{level}] 凭授权令牌放行 "
                    f"(level={grant.get('level')}, scope={grant.get('scope')}, "
                    f"expires={grant.get('expires_iso')})",
            phase="permission", accepted=True, reason="授权令牌放行")
    except Exception:
        pass
