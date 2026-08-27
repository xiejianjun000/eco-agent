#!/bin/bash
# ECO AGENT Profile 安装脚本
# 用法: bash install.sh
#
# 安装目标：~/.eco/profiles/eco-agent（eco 原生 profile 路径，eco chat 直接可用）
# Hermes Agent 为可选宿主：检测到 hermes CLI 时额外安装到 ~/.hermes/profiles/。

set -e

echo "🚀 安装 ECO AGENT Profile..."

SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"
ECO_PROFILE_DIR="$HOME/.eco/profiles/eco-agent"

# ── 主路径：安装到 eco 原生 profile 目录 ──
echo "📂 安装到 $ECO_PROFILE_DIR ..."
mkdir -p "$ECO_PROFILE_DIR/skills" "$ECO_PROFILE_DIR/memory-tree"
for f in config.yaml SOUL.md MEMORY.md USER.md PERMISSION.md; do
    if [ -f "$SOURCE_DIR/$f" ]; then
        cp "$SOURCE_DIR/$f" "$ECO_PROFILE_DIR/$f"
    else
        echo "⚠️  缺少文件 $SOURCE_DIR/$f，跳过"
    fi
done
cp -r "$SOURCE_DIR/../../skills/"* "$ECO_PROFILE_DIR/skills/" 2>/dev/null || true
echo "✅ eco profile 安装完成（eco chat 可直接使用 SOUL/PERMISSION 配置）"

# ── 可选：Hermes Agent 宿主 ──
if command -v hermes &> /dev/null; then
    HERMES_PROFILE_DIR="$HOME/.hermes/profiles/eco-agent"
    echo "📂 检测到 Hermes，同步安装到 $HERMES_PROFILE_DIR ..."
    if hermes profile list 2>/dev/null | grep -q "eco-agent"; then
        echo "📝 Profile 'eco-agent' 已存在，更新配置..."
    else
        echo "📝 创建 Profile 'eco-agent'..."
        hermes profile create eco-agent
    fi
    mkdir -p "$HERMES_PROFILE_DIR/skills" "$HERMES_PROFILE_DIR/memory-tree"
    cp "$ECO_PROFILE_DIR"/*.md "$ECO_PROFILE_DIR/config.yaml" "$HERMES_PROFILE_DIR/" 2>/dev/null || true
    cp -r "$ECO_PROFILE_DIR/skills/"* "$HERMES_PROFILE_DIR/skills/" 2>/dev/null || true
    echo "✅ Hermes profile 安装完成"
else
    echo "ℹ️  未检测到 Hermes CLI（可选宿主，跳过；eco 原生路径已完成安装）"
fi

echo ""
echo "使用方式："
echo "  eco chat                          # eco 原生 CLI"
echo "  eco setup                         # 首次使用配置 API Key"
if command -v hermes &> /dev/null; then
echo "  hermes --profile eco-agent        # Hermes 宿主模式"
fi
echo ""
echo "API Key 配置（写入 ~/.eco/.env）："
echo "  DEEPSEEK_API_KEY=sk-..."
echo "  KIMI_API_KEY=sk-..."
