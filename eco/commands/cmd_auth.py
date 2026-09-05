"""
eco auth - 非交互授权令牌管理（L4 等高级权限的脚本/CI 通道）

  eco auth grant --level L4 --ttl 3600 [--scope <tool|*>] [--role <角色>]   生成授权令牌
  eco auth revoke <id>                                       撤销授权
  eco auth list                                              列出授权（含过期/签名状态/角色）

角色维度（RBAC，SSO 前置）：grant 可指定角色（--role 或 env ECO_AUTH_ROLE），
角色写入授权体并参与签名（防篡改）；list 显示角色。
ECO_RBAC=1 时，grant 要求会话角色（env ECO_ROLE）具备 auth_grant 能力；
默认 ECO_RBAC 关闭，行为与之前完全一致。
"""

import os

from agent_core import grants as grants_mod
from agent_core import rbac


def run(args):
    action = getattr(args, "auth_action", None)
    if action == "grant":
        role = getattr(args, "role", None) or os.environ.get("ECO_AUTH_ROLE") or None
        try:
            g = rbac.grant_with_role(
                level=getattr(args, "level", "L4"),
                ttl=int(getattr(args, "ttl", 3600)),
                scope=getattr(args, "scope", "*") or "*",
                role=role,
            )
        except PermissionError as e:
            print(f"[auth] 拒绝: {e}")
            return 1
        except ValueError as e:
            print(f"[auth] 参数错误: {e}")
            return 1
        print(f"[auth] 已签发授权令牌 {g['id']}")
        role_txt = f" role={g['role']}" if g.get("role") else ""
        print(f"  level={g['level']} scope={g['scope']}{role_txt} expires={g['expires_iso']}")
        print(f"  文件: {grants_mod.GRANTS_DIR / (g['id'] + '.json')}")
        return 0
    if action == "revoke":
        gid = getattr(args, "grant_id", None)
        if not gid:
            print("[auth] 用法: eco auth revoke <grant-id>")
            return 1
        ok = grants_mod.revoke(gid)
        print(f"[auth] 已撤销 {gid}" if ok else f"[auth] 未找到授权: {gid}")
        return 0 if ok else 1
    if action == "sso":
        sub = getattr(args, "grant_id", None) or "status"
        if sub != "status":
            print(f"[auth] 未知 sso 子操作: {sub}（可用: status）")
            return 1
        return _sso_status()
    if action == "list" or action is None:
        gs = grants_mod.list_grants()
        if not gs:
            print(f"[auth] 暂无授权令牌（{grants_mod.GRANTS_DIR}）")
            return 0
        for g in gs:
            state = "过期" if g["_expired"] else ("有效" if g["_valid_sig"] else "签名无效")
            role_txt = f" role={g['role']}" if g.get("role") else ""
            print(
                f"  {g['id']}  level={g['level']} scope={g.get('scope', '*')}{role_txt} "
                f"expires={g.get('expires_iso', '?')}  [{state}]"
            )
        return 0
    print(f"[auth] 未知操作: {action}")
    return 1


def _sso_status():
    """eco auth sso status — 显示 SSO 配置状态（secret 脱敏，discovery 可达性）"""
    from agent_core import sso as sso_mod

    cfg = sso_mod.OIDCConfig.from_env()
    print(f"[auth sso] enabled={'是' if cfg.enabled else '否（ECO_SSO=1 开启）'}")
    print(f"  protocol={cfg.protocol}  issuer={cfg.issuer or '(未配置)'}")
    print(f"  client_id={cfg.client_id or '(未配置)'}  client_secret={cfg.masked_secret()}")
    print(f"  redirect_uri={cfg.redirect_uri or '(未配置)'}  scopes={' '.join(cfg.scopes)}")
    print(f"  role_claim={cfg.role_claim}  session_ttl={cfg.session_ttl}s")
    if cfg.protocol == "cas":
        print(f"  cas_validate_url={cfg.cas_validate_url or '(未配置)'}")
        return 0
    if not cfg.issuer:
        print("  discovery=跳过（未配置 issuer）")
        return 0
    try:
        doc = sso_mod.OIDCProvider(cfg, timeout=3).discover()
        print(f"  discovery=可达 authorization_endpoint={doc.get('authorization_endpoint', '?')}")
        return 0
    except Exception as e:
        print(f"  discovery=不可达（{e}）")
        return 1
