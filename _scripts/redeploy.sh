#!/usr/bin/env bash
# _scripts/redeploy.sh — eco-agent 一键体检/测试/构建/重启
#
# 用法:
#   bash _scripts/redeploy.sh              # 快速体检 + 关键测试 + 构建前端（不重启）
#   bash _scripts/redeploy.sh --restart    # 额外重启本机 8321 服务
#   bash _scripts/redeploy.sh --full       # 全量测试（约 8-10 分钟）
set -e
cd "$(dirname "$0")/.."

echo "═══ 1/4 健康自检 ═══"
python3 _scripts/health_check.py --live || true

echo ""
echo "═══ 2/4 测试 + 契约门禁 ═══"
if [ "$1" == "--full" ] || [ "$2" == "--full" ]; then
    python3 -m pytest tests/ -q
else
    python3 -m pytest \
        tests/modules/test_tool_wiring.py \
        tests/modules/test_govmcp_platforms.py \
        tests/modules/test_prompt_sections.py \
        tests/modules/test_prompt_engine.py \
        tests/modules/test_mcp_connector.py \
        tests/modules/test_tools_schema_quality.py \
        tests/modules/test_capability_consistency.py \
        tests/modules/test_skill_meta.py \
        tests/modules/test_llm_client.py -q
fi
# 契约门禁①：评测集机械校验（引用真实性，虚构法条必挂）
python3 _scripts/run_evals.py --mechanical
# 契约门禁②：技能全库自审（≥70 分）
python3 ecoskills/meta-audit/scripts/audit.py --all

echo ""
echo "═══ 3/4 构建前端 ═══"
(cd web && npm_config_cache=/tmp/npm-cache-pw npm run build 2>&1 | tail -2)

if [ "$1" == "--restart" ] || [ "$2" == "--restart" ]; then
    echo ""
    echo "═══ 4/4 重启服务 ═══"
    pkill -f "eco.cli server" 2>/dev/null || true
    sleep 1
    nohup python3 -m eco.cli server --port 8321 > /tmp/eco-server.log 2>&1 &
    sleep 6
    curl -s http://127.0.0.1:8321/healthz && echo " ← 服务已就绪（日志: /tmp/eco-server.log）"
else
    echo ""
    echo "═══ 4/4 跳过重启（加 --restart 重启 8321 服务）═══"
fi
echo "完成。"
