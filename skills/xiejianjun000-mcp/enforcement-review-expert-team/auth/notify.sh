#!/bin/bash
# [已废弃] 2026-08-08 — 告警由 hermes cron deliver 投递到消息平台
# 请配置 ECOAEGIS_NOTIFY_CHANNEL 环境变量启用 hermes 原生告警
# 原用途: 告警通知链 — agent-mail → alerts/ 落盘 → DDL 兜底
# 原用法: ./notify.sh <platform_id> <severity> <title> <body>

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ALERTS_DIR="$SCRIPT_DIR/alerts"

PLATFORM="${1:?missing platform}"
SEVERITY="${2:-WARNING}"
TITLE="${3:-告警}"
BODY="${4:-无详情}"

mkdir -p "$ALERTS_DIR"

# 去重：同一平台同一 severity 24h 内只发一次
shopt -s nullglob
LAST_ALERT=$(ls -t "$ALERTS_DIR"/alert_${PLATFORM}_*.json 2>/dev/null | head -1 || echo "")
shopt -u nullglob
if [ -n "$LAST_ALERT" ]; then
    LAST_TIME=$(python3 -c "import os,json;print(json.load(open('$LAST_ALERT')).get('timestamp',''))" 2>/dev/null || echo "")
    if [ -n "$LAST_TIME" ]; then
        NOW_TS=$(date +%s)
        LAST_TS=$(date -jf "%Y-%m-%dT%H:%M:%SZ" "$LAST_TIME" +%s 2>/dev/null || echo 0)
        if [ $((NOW_TS - LAST_TS)) -lt 86400 ]; then
            echo "[NOTIFY] 24h 内已有同平台告警，跳过发送"
            exit 0
        fi
    fi
fi

# 链式通知：agent-mail → 落盘 → stderr
echo "[NOTIFY] $SEVERITY: $TITLE"
echo "[NOTIFY] $BODY"

# 1. 尝试 agent-mail（如果可用）
if command -v agent-mail &>/dev/null; then
    echo "Trying agent-mail..."
    # agent-mail send --title "$TITLE" --body "$BODY" --severity "$SEVERITY" 2>/dev/null && exit 0
    echo "[NOTIFY] agent-mail 路径存在但发送待实现"
fi

# 2. 降级：落盘到 alerts/ 目录
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
ALERT_FILE="$ALERTS_DIR/alert_${PLATFORM}_${TS//:/}.json"
python3 -c "
import json
alert = {
    'platform': '$PLATFORM',
    'title': '''$TITLE''',
    'body': '''$BODY''',
    'severity': '$SEVERITY',
    'timestamp': '$TS'
}
with open('$ALERT_FILE', 'w') as f:
    json.dump(alert, f, indent=2, ensure_ascii=False)
print('Alert saved to $ALERT_FILE')
"

# 3. 终级兜底：写 stderr（DDL 日环会扫描）
echo "[NOTIFY] 告警已写入: $ALERT_FILE" >&2

echo "[NOTIFY] done: $ALERT_FILE"
