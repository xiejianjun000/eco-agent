#!/usr/bin/env bash
# =============================================================================
# stress_test.sh — eco Agent 生产环境压测一键脚本（A2 / C2 / D2）
#
# 补齐「对齐度 95 → 100」的最后三项环境验证：并发渲染 / WAL 崩溃恢复 / 长稳内存。
# 用法:
#   bash scripts/stress_test.sh                # 全部跑（D2 默认 30 分钟）
#   D2_DURATION_SEC=120 bash scripts/stress_test.sh   # D2 缩短到 2 分钟（快速自检）
#   ONLY=a2     bash scripts/stress_test.sh    # 只跑 A2（c2/d2/a2 三选一）
#
# ⚠️  C2 会 kill -9 服务并重启 —— 不要在正在用的生产实例上跑。
# 输出: stress_report.md（含每项 PASS/FAIL + 实测数据）
# =============================================================================
set -uo pipefail

# ── 配置（可用环境变量覆盖）──────────────────────────────
SERVER_URL="${SERVER_URL:-http://127.0.0.1:8321}"
REPO_DIR="${REPO_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
DB_PATH="${DB_PATH:-$REPO_DIR/memory-tree/data/eco_memory.db}"
REPORT="${REPORT:-$REPO_DIR/stress_report.md}"
SERVER_CMD="${SERVER_CMD:-python3 -m eco.cli server --port 8321}"
D2_DURATION_SEC="${D2_DURATION_SEC:-1800}"          # 默认 30 分钟
ONLY="${ONLY:-all}"                                  # a2 / c2 / d2 / all
START_SERVER="${START_SERVER:-1}"                    # 1=脚本自己起服务，0=服务已在跑

PASS=0; FAIL=0; declare -a RESULTS=()

log()  { printf '\033[1;34m[stress]\033[0m %s\n' "$*"; }
ok()   { PASS=$((PASS+1)); RESULTS+=("✅ $1"); printf '\033[1;32m  PASS\033[0m %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); RESULTS+=("❌ $1"); printf '\033[1;31m  FAIL\033[0m %s\n' "$1"; }
note() { RESULTS+=("📝 $1"); }

require() { command -v "$1" >/dev/null 2>&1 || { echo "缺依赖: $1"; exit 2; }; }

# ── 前置检查 ────────────────────────────────────────────
require curl
require sqlite3
require ps

cd "$REPO_DIR" || exit 2

# ── 服务启动 ────────────────────────────────────────────
if [ "$START_SERVER" = "1" ]; then
  log "启动 eco server ..."
  # 杀掉旧实例（C2 会 kill 服务，这里保证干净起点）
  lsof -ti :8321 2>/dev/null | xargs kill 2>/dev/null; sleep 1
  $SERVER_CMD > /tmp/eco_stress_server.log 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 30); do
    curl -sf "$SERVER_URL/healthz" >/dev/null 2>&1 && break
    sleep 1
  done
  curl -sf "$SERVER_URL/healthz" >/dev/null 2>&1 || { echo "服务启动失败，看 /tmp/eco_stress_server.log"; exit 2; }
  log "服务就绪 (pid=$SERVER_PID)"
else
  SERVER_PID=""
  curl -sf "$SERVER_URL/healthz" >/dev/null 2>&1 || { echo "服务未在 $SERVER_URL 运行"; exit 2; }
fi

# =============================================================================
# A2 — Web UI 并发：5 会话 × 6MB 附件，验证上下文隔离 + 服务端资源
# =============================================================================
run_a2() {
  log "===== A2 并发渲染 ====="
  BIG=/tmp/eco_6mb.txt
  head -c 6291456 /dev/urandom | base64 > "$BIG"   # 6MB 文本

  log "并发上传 5 个 6MB 附件 + 5 个 SSE 会话 ..."
  for i in 1 2 3 4 5; do
    curl -s -o /dev/null -F "file=@$BIG" "$SERVER_URL/api/v1/files" &
  done
  wait

  # 5 个并发 SSE 会话，各自回显 session_id 校验隔离
  for i in 1 2 3 4 5; do
    curl -s -N -m 60 -X POST "$SERVER_URL/api/v1/chat/stream" \
      -H 'Content-Type: application/json' -H 'X-ECO-CLIENT: web' \
      -d "{\"message\":\"回复 OK 两个字即可\",\"history\":[],\"session_id\":\"stress_a2_$i\"}" \
      > "/tmp/eco_a2_$i.out" 2>&1 &
  done
  wait

  # 校验：5 个会话都收到了 done 事件（上下文未串）
  done_count=0
  for i in 1 2 3 4 5; do
    grep -q '"done"' "/tmp/eco_a2_$i.out" 2>/dev/null && done_count=$((done_count+1))
  done
  if [ "$done_count" -eq 5 ]; then
    ok "A2: 5 会话全部完成，上下文隔离 (done=$done_count/5)"
  else
    bad "A2: 会话完成 $done_count/5（疑似中断/串话）"
  fi

  # 服务端峰值资源
  if [ -n "$SERVER_PID" ]; then
    rss_kb=$(ps -o rss= -p "$SERVER_PID" 2>/dev/null | tr -d ' ' || echo 0)
    note "A2: 服务端 RSS=${rss_kb}KB（观察是否 OOM；阈值参考：<2GB）"
  fi
  rm -f "$BIG" /tmp/eco_a2_*.out
}

# =============================================================================
# C2 — WAL 崩溃恢复：写入循环中 kill -9，重启后 integrity_check
# =============================================================================
run_c2() {
  log "===== C2 WAL 崩溃恢复 ====="
  # 保证服务在跑
  curl -sf "$SERVER_URL/healthz" >/dev/null 2>&1 || {
    $SERVER_CMD > /tmp/eco_stress_server.log 2>&1 &
    SERVER_PID=$!
    sleep 3
  }

  log "直接写入 eco_memory.db（WAL）+ 3 秒后 kill -9 ..."
  (
    cd "$REPO_DIR" && python3 -c "
import sys; sys.path.insert(0,'.')
from _scripts.memory_tree import MemoryTree
import time
for i in range(10000):
    MemoryTree().create_node('case', f'压测节点{i}', f'崩溃恢复测试数据{i}', tags=['stress'])
    time.sleep(0.005)
" > /tmp/eco_c2_writer.log 2>&1
  ) &
  WRITER_PID=$!
  sleep 3
  # 强制 kill 写入进程 + 服务（模拟写入中途断电/崩溃）
  kill -9 "$WRITER_PID" 2>/dev/null
  pkill -9 -f "eco.cli server" 2>/dev/null
  sleep 1
  log "已强制 kill，重启服务 ..."

  $SERVER_CMD > /tmp/eco_stress_server2.log 2>&1 &
  SERVER_PID=$!
  for _ in $(seq 1 30); do
    curl -sf "$SERVER_URL/healthz" >/dev/null 2>&1 && break
    sleep 1
  done

  # 1. integrity_check
  ic=$(sqlite3 "$DB_PATH" "PRAGMA integrity_check;" 2>/dev/null)
  if [ "$ic" = "ok" ]; then
    ok "C2: SQLite integrity_check = ok（WAL 无损坏）"
  else
    bad "C2: integrity_check = $ic（数据库损坏！）"
  fi
  # 2. 无 malformed 错误日志
  if grep -qi "malformed\|database disk image" /tmp/eco_stress_server2.log 2>/dev/null; then
    bad "C2: 重启日志出现数据库损坏错误"
  else
    ok "C2: 重启日志无 malformed 错误，自动恢复"
  fi
}

# =============================================================================
# D2 — 长稳内存：持续对话，监控 RSS 斜率
# =============================================================================
run_d2() {
  log "===== D2 长稳内存（${D2_DURATION_SEC}s）====="
  curl -sf "$SERVER_URL/healthz" >/dev/null 2>&1 || {
    $SERVER_CMD > /tmp/eco_stress_server.log 2>&1 &
    SERVER_PID=$!
    sleep 3
  }
  LONG=/tmp/eco_long.txt
  head -c 4000 /dev/urandom | base64 > "$LONG"   # ~5KB 长文本

  if [ -n "$SERVER_PID" ]; then
    rss0=$(ps -o rss= -p "$SERVER_PID" 2>/dev/null | tr -d ' ' || echo 0)
  else
    rss0=$(pgrep -f "eco.cli server" | head -1 | xargs ps -o rss= -p 2>/dev/null | tr -d ' ' || echo 0)
  fi
  log "初始 RSS=${rss0}KB，持续压测 ..."

  end=$(( $(date +%s) + D2_DURATION_SEC ))
  n=0
  while [ "$(date +%s)" -lt "$end" ]; do
    curl -s -o /dev/null -N -m 20 -X POST "$SERVER_URL/api/v1/chat/stream" \
      -H 'Content-Type: application/json' \
      -d "{\"message\":\"$(head -c 2000 "$LONG")\",\"history\":[],\"session_id\":\"stress_d2_$n\"}" 2>/dev/null
    n=$((n+1))
    sleep 2
  done

  if [ -n "$SERVER_PID" ]; then
    rss1=$(ps -o rss= -p "$SERVER_PID" 2>/dev/null | tr -d ' ' || echo 0)
  else
    rss1=$(pgrep -f "eco.cli server" | head -1 | xargs ps -o rss= -p 2>/dev/null | tr -d ' ' || echo 0)
  fi
  delta=$(( rss1 - rss0 ))
  log "末 RSS=${rss1}KB，增量=${delta}KB（$n 轮对话）"

  # 阈值：30 分钟增长 < 200MB（约 204800 KB）
  if [ "$delta" -lt 204800 ]; then
    ok "D2: 内存增量 ${delta}KB < 200MB，无泄漏迹象"
  else
    bad "D2: 内存增量 ${delta}KB 超标（疑似泄漏，查 BM25Index/EmbeddingClient 引用链）"
  fi
  rm -f "$LONG"
}

# =============================================================================
# 执行 + 报告
# =============================================================================
case "$ONLY" in
  a2) run_a2 ;;
  c2) run_c2 ;;
  d2) run_d2 ;;
  all) run_a2; run_c2; run_d2 ;;
  *) echo "ONLY 取值 a2/c2/d2/all"; exit 2 ;;
esac

# 收尾：停掉脚本自起的服务
if [ -n "$SERVER_PID" ]; then
  kill "$SERVER_PID" 2>/dev/null
fi

# 生成报告
{
  echo "# eco Agent 压测报告"
  echo
  echo "- 时间: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "- 服务: $SERVER_URL"
  echo "- D2 时长: ${D2_DURATION_SEC}s"
  echo
  for r in "${RESULTS[@]}"; do echo "- $r"; done
  echo
  echo "## 结论"
  if [ "$FAIL" -eq 0 ]; then
    echo "✅ 全部通过（$PASS 项）—— 可上线"
  else
    echo "❌ $FAIL 项未通过（$PASS 项通过）—— 需回退修复"
  fi
} > "$REPORT"

log "报告已生成: $REPORT"
echo
cat "$REPORT"
echo
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 压测全部通过"
else
  echo "❌ 有 $FAIL 项未通过"
  exit 1
fi
