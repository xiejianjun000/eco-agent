#!/bin/bash
# ──────────────────────────────────────────────────────────
# EcoAegis Hermes 集成安装脚本
# 将 EcoAegis AuthService 注册到 hermes-agent 后端
# ──────────────────────────────────────────────────────────
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_DIR="$HERMES_HOME/plugins/ecoaegis"
SKILL_DIR="$HERMES_HOME/skills/ecoaegis-auth"

echo "=== EcoAegis Hermes 集成安装 ==="

# 1. 安装插件到 ~/.hermes/plugins/
echo "[1/4] 安装 ecoaegis 插件..."
mkdir -p "$PLUGIN_DIR"
cp "$PROJECT_DIR/hermes-plugins/ecoaegis/"* "$PLUGIN_DIR/"
echo "  -> $PLUGIN_DIR/"

# 2. 安装 SKILL.md
echo "[2/4] 安装技能文件..."
mkdir -p "$SKILL_DIR"
cp "$PROJECT_DIR/docs/skills/ecoaegis-auth/SKILL.md" "$SKILL_DIR/SKILL.md"
echo "  -> $SKILL_DIR/SKILL.md"

# 3. 设置 cron 作业
echo "[3/4] 注册 cron 作业..."
echo ""
echo "请在 hermes CLI 中依次执行以下命令（或由 hermes agent 执行 auth_setup_cron）："
echo ""

cat <<'CRON_CMDS'
# 每日三次心跳检测
hermes cron create "50 7 * * *" \
  "用 auth_health 检测所有环保平台的登录会话状态。如有 critical 状态（EXPIRED/NO_STATE），立即触发 auth_login 重新登录并投递告警。" \
  --name ecoaegis-heartbeat-morning

hermes cron create "0 14 * * *" \
  "用 auth_health 检测所有环保平台的登录会话状态。如有 critical 状态（EXPIRED/NO_STATE），立即触发 auth_login 重新登录并投递告警。" \
  --name ecoaegis-heartbeat-noon

hermes cron create "0 19 * * *" \
  "用 auth_health 检测所有环保平台的登录会话状态。如有 critical 状态（EXPIRED/NO_STATE），立即触发 auth_login 重新登录并投递告警。" \
  --name ecoaegis-heartbeat-evening

# 每周一完整凭据验证
hermes cron create "0 8 * * 1" \
  "对大气监督帮扶平台执行完整凭据验证登录。调用 auth_login atmosphere，成功后导出新的 storageState。" \
  --name ecoaegis-login-atmosphere-weekly
CRON_CMDS

echo ""

# 4. 提示工具集启用
echo "[4/4] 启用 ecoaegis 工具集..."
echo "  在 hermes 中执行: hermes tools"
echo "  勾选 ecoaegis 工具集"
echo ""
echo "=== 安装完成 ==="
echo "验证: 在 hermes 对话中输入 '用 auth_health 检测所有平台'"
