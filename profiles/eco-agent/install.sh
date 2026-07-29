#!/bin/bash
# ECO AGENT Hermes Profile 安装脚本
# 用法: bash install.sh

set -e

echo "🚀 安装 ECO AGENT Hermes Profile..."

HERMES_PROFILES_DIR="$HOME/.hermes/profiles"
ECO_PROFILE_DIR="$HERMES_PROFILES_DIR/eco-agent"
SOURCE_DIR="$(cd "$(dirname "$0")" && pwd)"

# 检查 Hermes 是否已安装
if ! command -v hermes &> /dev/null; then
    echo "⚠️  Hermes Agent 未检测到，请先安装："
    echo "   pip install hermes-agent"
    echo "   或参考: https://github.com/NousResearch/hermes-agent"
    echo ""
    echo "安装完成后重新运行本脚本。"
    exit 1
fi

# 检查是否已有 eco-agent profile
if hermes profile list 2>/dev/null | grep -q "eco-agent"; then
    echo "📝 Profile 'eco-agent' 已存在，更新配置..."
else
    echo "📝 创建 Profile 'eco-agent'..."
    hermes profile create eco-agent
fi

# 复制配置文件
echo "📂 复制配置文件..."
cp "$SOURCE_DIR/config.yaml" "$ECO_PROFILE_DIR/config.yaml"
cp "$SOURCE_DIR/SOUL.md" "$ECO_PROFILE_DIR/SOUL.md"
cp "$SOURCE_DIR/MEMORY.md" "$ECO_PROFILE_DIR/MEMORY.md"
cp "$SOURCE_DIR/USER.md" "$ECO_PROFILE_DIR/USER.md"
cp "$SOURCE_DIR/PERMISSION.md" "$ECO_PROFILE_DIR/PERMISSION.md"

# 创建 skills 目录
mkdir -p "$ECO_PROFILE_DIR/skills"
cp -r "$SOURCE_DIR/../../skills/"* "$ECO_PROFILE_DIR/skills/" 2>/dev/null || true

# 创建 memory-tree 目录
mkdir -p "$ECO_PROFILE_DIR/memory-tree"

echo ""
echo "✅ ECO AGENT Profile 安装完成！"
echo ""
echo "使用方式："
echo "  hermes --profile eco-agent              # CLI 模式"
echo "  hermes --profile eco-agent --mode chat  # 对话模式"
echo ""
echo "首次使用前请设置 API Key："
echo "  export ANTHROPIC_API_KEY=sk-..."
echo "  # 或写入 ~/.hermes/profiles/eco-agent/.env"
