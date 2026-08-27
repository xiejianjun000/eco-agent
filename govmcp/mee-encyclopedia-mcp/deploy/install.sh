#!/usr/bin/env bash
# 生产部署脚本：安装依赖、构建、冒烟、注册 systemd 服务（可选）。
# 用法: bash deploy/install.sh [--with-service]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[1/4] 创建虚拟环境"
python3 -m venv .venv
source .venv/bin/activate

echo "[2/4] 安装依赖"
pip install --upgrade pip
pip install -e .

echo "[3/4] 运行冒烟测试"
python tests/test_smoke.py

echo "[4/4] 部署完成"
if [[ "${1:-}" == "--with-service" ]]; then
    echo "注册 systemd 服务..."
    sudo cp deploy/mee-encyclopedia-mcp.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable mee-encyclopedia-mcp
    sudo systemctl start mee-encyclopedia-mcp
    systemctl status mee-encyclopedia-mcp --no-pager
else
    echo "提示：如需注册为系统服务，执行 bash deploy/install.sh --with-service"
fi

echo "启动方式（MCP stdio）: .venv/bin/mee-encyclopedia-mcp --transport stdio"
