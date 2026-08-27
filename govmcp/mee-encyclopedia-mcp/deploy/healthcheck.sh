#!/usr/bin/env bash
# 健康检查：验证 MCP 进程与核心只读能力。
# 用法: bash deploy/healthcheck.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== 进程检查 =="
if pgrep -f "mee-encyclopedia.server" >/dev/null 2>&1 || pgrep -f "mee-encyclopedia-mcp" >/dev/null 2>&1; then
    echo "PASS: MCP 进程在运行"
else
    echo "WARN: 未发现 MCP 进程（若由 MCP 客户端托管则属正常）"
fi

echo "== 导入与工具数 =="
if PYTHONPATH=src .venv/bin/python -c "
from mee_encyclopedia.server import mcp
n = len(mcp._tool_manager._tools)
print(f'tools={n}')
assert n >= 45, 'tool count too low'
" 2>/dev/null || PYTHONPATH=src python3 -c "
from mee_encyclopedia.server import mcp
n = len(mcp._tool_manager._tools)
print(f'tools={n}')
assert n >= 45, 'tool count too low'
"; then
    echo "PASS: 工具注册正常（>=45）"
else
    echo "FAIL: 工具注册异常"; exit 1
fi

echo "== 网络只读连通 =="
if PYTHONPATH=src .venv/bin/python -c "
from mee_encyclopedia.server import read_mee_list
r = read_mee_list('要闻动态', limit=3)
print('items=', len(r.get('items', [])))
" 2>/dev/null || PYTHONPATH=src python3 -c "
from mee_encyclopedia.server import read_mee_list
r = read_mee_list('要闻动态', limit=3)
print('items=', len(r.get('items', [])))
"; then
    echo "PASS: 官网栏目读取正常"
else
    echo "WARN: 官网读取失败（网络或站点变化）"
fi

echo "健康检查完成"
