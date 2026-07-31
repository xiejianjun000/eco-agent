#!/usr/bin/env bash
# build_offline.sh — 在有网机器上构建 ECO AGENT 离线部署包。
#
# 产物: dist/eco-offline-<version>.tar.gz
#   ├── offline_wheels/    全部依赖的 wheel（pip download）
#   ├── eco-agent/         项目源码
#   └── install.sh         内网无网安装脚本
#
# 用法: bash deploy/offline/build_offline.sh [输出目录]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT_DIR="${1:-$ROOT/dist}"
VERSION="$(date +%Y%m%d)-r15"
PKG="eco-offline-${VERSION}"
STAGE="${OUT_DIR}/${PKG}"

PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "[1/4] 准备构建目录 ${STAGE}"
rm -rf "${STAGE}"
mkdir -p "${STAGE}/offline_wheels" "${STAGE}/eco-agent"

echo "[2/4] 下载依赖 wheel 到 offline_wheels/"
"${PYTHON_BIN}" -m pip download \
    -r "${ROOT}/requirements.txt" \
    -d "${STAGE}/offline_wheels" \
    --only-binary=:all: || "${PYTHON_BIN}" -m pip download \
    -r "${ROOT}/requirements.txt" \
    -d "${STAGE}/offline_wheels"
# 构建后端 wheel：供内网 pip install -e .（--no-build-isolation）离线可用
"${PYTHON_BIN}" -m pip download setuptools wheel \
    -d "${STAGE}/offline_wheels" --only-binary=:all: || true

echo "[3/4] 拷贝项目源码（排除测试/文档/缓存）"
tar -C "${ROOT}" \
    --exclude='./.git' --exclude='./tests' --exclude='./docs' \
    --exclude='./output' --exclude='./backup' --exclude='./dist' \
    --exclude='./__pycache__' --exclude='./.pytest_cache' \
    --exclude='./*.tgz' \
    -cf - . | tar -C "${STAGE}/eco-agent" -xf -

echo "[4/4] 写入 install.sh 并打包"
cat > "${STAGE}/install.sh" <<'INSTALL_EOF'
#!/usr/bin/env bash
# ECO AGENT 离线安装脚本（内网无网环境）
# 用法: sudo bash install.sh [--prefix /opt/eco] [--user eco]
set -euo pipefail

PREFIX="/opt/eco"
SVC_USER="eco"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prefix) PREFIX="$2"; shift 2 ;;
        --user)   SVC_USER="$2"; shift 2 ;;
        *) echo "未知参数: $1" >&2; exit 1 ;;
    esac
done

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[install] 创建用户 ${SVC_USER}（如不存在）"
id -u "${SVC_USER}" >/dev/null 2>&1 || useradd --system --create-home "${SVC_USER}" || true

echo "[install] 安装项目到 ${PREFIX}"
mkdir -p "${PREFIX}"
cp -r "${HERE}/eco-agent/." "${PREFIX}/"

echo "[install] 创建 venv 并从本地 wheel 安装依赖（离线）"
python3 -m venv "${PREFIX}/venv"
"${PREFIX}/venv/bin/pip" install --no-index \
    --find-links "${HERE}/offline_wheels" \
    -r "${PREFIX}/requirements.txt"

echo "[install] 安装 eco 包到 venv（eco 命令任意目录可用）"
# D2：editable 安装提供 console entry（pyproject [project.scripts] eco = "eco.cli:main"）。
# 3.12+ venv 默认无 setuptools，先从本地 wheel 补装后用 --no-build-isolation 离线构建。
if "${PREFIX}/venv/bin/pip" install --no-index --find-links "${HERE}/offline_wheels" setuptools wheel \
    && "${PREFIX}/venv/bin/pip" install --no-index --no-build-isolation \
        --find-links "${HERE}/offline_wheels" -e "${PREFIX}"; then
    echo "[install] eco 命令: ${PREFIX}/venv/bin/eco"
else
    # 降级：手工生成 console entry 包装脚本（PYTHONPATH 指向源码，任意目录可运行）
    echo "[warn] editable 安装失败，改用手工 eco 入口脚本" >&2
    cat > "${PREFIX}/venv/bin/eco" <<EOF
#!/bin/sh
PYTHONPATH="${PREFIX}\${PYTHONPATH:+:\$PYTHONPATH}" exec "${PREFIX}/venv/bin/python" -m eco.cli "\$@"
EOF
    chmod +x "${PREFIX}/venv/bin/eco"
fi

echo "[install] 安装沙箱依赖 bubblewrap/slirp4netns（需系统包管理器或预装）"
if command -v apt-get >/dev/null 2>&1; then
    apt-get install -y bubblewrap slirp4netns || \
        echo "[warn] 系统包安装失败，请离线预装 bubblewrap 与 slirp4netns" >&2
else
    echo "[warn] 非 apt 系统，请手动安装 bubblewrap 与 slirp4netns" >&2
fi

echo "[install] 安装 systemd unit"
if [[ "${EUID}" -ne 0 ]]; then
    # D1：无 root 时不得让 set -e 因 /etc/systemd/system 不可写而整体 exit=1，
    # 依赖与源码已装好，降级为手动启动提示并正常结束。
    echo "[warn] 非 root 用户，跳过 systemd unit 安装" >&2
    echo "       请手动用 nohup/tmux 启动，命令：" >&2
    echo "         cd ${PREFIX} && set -a && . ~/.eco/.env && set +a && \\" >&2
    echo "         nohup ${PREFIX}/venv/bin/eco gateway start --port 7070 >> gateway.log 2>&1 &" >&2
elif [[ -d /etc/systemd/system ]]; then
    cp "${PREFIX}/deploy/systemd/eco-gateway.service" /etc/systemd/system/
    sed -i "s|/opt/eco|${PREFIX}|g; s|User=eco|User=${SVC_USER}|g" \
        /etc/systemd/system/eco-gateway.service
    systemctl daemon-reload || true
    echo "[install] 完成。启动: systemctl enable --now eco-gateway"
else
    echo "[warn] 未检测到 systemd，跳过 unit 安装" >&2
fi

chown -R "${SVC_USER}:${SVC_USER}" "${PREFIX}" || true
echo "[install] 手动验证: ${PREFIX}/venv/bin/eco --help（或 python -m eco.cli --version）"
INSTALL_EOF
chmod +x "${STAGE}/install.sh"

tar -C "${OUT_DIR}" -czf "${OUT_DIR}/${PKG}.tar.gz" "${PKG}"
echo "完成: ${OUT_DIR}/${PKG}.tar.gz"
