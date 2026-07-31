"""
eco auth - 非交互授权令牌管理（L4 等高级权限的脚本/CI 通道）

  eco auth grant --level L4 --ttl 3600 [--scope <tool|*>]   生成授权令牌
  eco auth revoke <id>                                       撤销授权
  eco auth list                                              列出授权（含过期/签名状态）
"""
from agent_core import grants as grants_mod


def run(args):
    action = getattr(args, "auth_action", None)
    if action == "grant":
        g = grants_mod.grant(level=getattr(args, "level", "L4"),
                             ttl=int(getattr(args, "ttl", 3600)),
                             scope=getattr(args, "scope", "*") or "*")
        print(f"[auth] 已签发授权令牌 {g['id']}")
        print(f"  level={g['level']} scope={g['scope']} expires={g['expires_iso']}")
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
    if action == "list" or action is None:
        gs = grants_mod.list_grants()
        if not gs:
            print(f"[auth] 暂无授权令牌（{grants_mod.GRANTS_DIR}）")
            return 0
        for g in gs:
            state = "过期" if g["_expired"] else ("有效" if g["_valid_sig"] else "签名无效")
            print(f"  {g['id']}  level={g['level']} scope={g.get('scope', '*')} "
                  f"expires={g.get('expires_iso', '?')}  [{state}]")
        return 0
    print(f"[auth] 未知操作: {action}")
    return 1
