#!/bin/bash
# [已废弃] 2026-08-08 — 已迁移至 hermes 插件
# 请使用 hermes cron + auth_health 工具替代系统 crontab
# 安装: bash scripts/setup-hermes.sh
# 原用途: auth-health 心跳检测 — 定时任务入口
# 原用法: ./heartbeat.sh [atmosphere|water|all]
# 原 crontab: 0 7 * * * cd /Users/mac/EcoAegis && ./auth/heartbeat.sh all

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
STATE_DIR="$SCRIPT_DIR/state"
ALERTS_DIR="$SCRIPT_DIR/alerts"
PYTHON="$SCRIPT_DIR/venv/bin/python"

mkdir -p "$STATE_DIR" "$ALERTS_DIR"

PLATFORM="${1:-all}"
RET=0

heartbeat_one() {
    local platform_id="$1"
    local state_file="$STATE_DIR/${platform_id}.json"
    local storage_file="$STATE_DIR/${platform_id}.storageState.json"

    echo "=== $(date '+%H:%M:%S') heartbeat: $platform_id ==="

    # 1. 轻量会话探针（HTTP 级）
    if [ -f "$storage_file" ]; then
        $PYTHON "$SCRIPT_DIR/probe_session.py" "$platform_id" "$storage_file" 2>&1 || true
    else
        echo "[SKIP] $platform_id: 无 storageState，跳过轻量探针"
    fi

    # 2. 检查是否有未处理告警
    local alert_count=$(ls "$ALERTS_DIR"/alert_${platform_id}_*.json 2>/dev/null | wc -l | tr -d ' ')
    if [ "$alert_count" -gt 0 ]; then
        echo "[ALERTS] $platform_id: $alert_count 条未处理告警"
    fi

    echo ""
}

case "$PLATFORM" in
    all)
        heartbeat_one atmosphere
        heartbeat_one water
        ;;
    atmosphere|water)
        heartbeat_one "$PLATFORM"
        ;;
    *)
        echo "Usage: $0 [atmosphere|water|all]"
        exit 1
        ;;
esac

echo "=== heartbeat done ==="
exit $RET
