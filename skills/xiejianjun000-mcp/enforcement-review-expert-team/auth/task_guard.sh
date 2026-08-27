#!/bin/bash
# [已废弃] 2026-08-08 — hermes cron 内置超时 + 任务守卫机制
# 请使用 hermes cron create 注册定时任务替代
# 原用途: 定时任务守卫 — 超时保护 + 产物自检 + 失败告警
# 原用法: ./task_guard.sh <task_name> <platform_id> <expected_product_glob> <command...>
# 原示例: ./task_guard.sh "大气帮扶跟踪" atmosphere "大气帮扶跟踪报告_*.md" node patrol_scanner.js

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

TASK_NAME="${1:?missing task_name}"
PLATFORM="${2:?missing platform_id}"
PRODUCT_GLOB="${3:?missing product_glob}"
shift 3
CMD=("$@")

TIMEOUT_SEC=600
START_TIME=$(date +%s)

echo "=== $(date '+%Y-%m-%d %H:%M:%S') task_guard: $TASK_NAME ==="

# 运行任务
EXIT_CODE=0
timeout $TIMEOUT_SEC "${CMD[@]}" || EXIT_CODE=$?

ELAPSED=$(( $(date +%s) - START_TIME ))

# 产物自检
PRODUCT_FOUND=0
if ls $PRODUCT_GLOB 2>/dev/null | grep -q .; then
    # 检查产物是否是今天的
    TODAY=$(date +%Y%m%d)
    for f in $PRODUCT_GLOB; do
        if [ -f "$f" ]; then
            MTIME=$(date -r "$f" +%Y%m%d 2>/dev/null || echo "")
            if [ "$MTIME" = "$TODAY" ]; then
                PRODUCT_FOUND=1
                break
            fi
        fi
    done
fi

if [ $EXIT_CODE -ne 0 ] || [ $PRODUCT_FOUND -eq 0 ]; then
    echo "[GUARD] $TASK_NAME 异常 (exit=$EXIT_CODE, product_found=$PRODUCT_FOUND, elapsed=${ELAPSED}s)"

    # 生成告警内容
    ALERT_BODY="${TASK_NAME}
耗时: ${ELAPSED}s
退出码: ${EXIT_CODE}
产物: $([ $PRODUCT_FOUND -eq 1 ] && echo '已生成' || echo '未生成')
平台: $PLATFORM
时间: $(date '+%Y-%m-%d %H:%M:%S')"

    "$SCRIPT_DIR/notify.sh" "$PLATFORM" "WARNING" "${TASK_NAME} 异常" "$ALERT_BODY"

    exit 1
fi

echo "[GUARD] $TASK_NAME 正常完成 (${ELAPSED}s)"
exit 0
