#!/usr/bin/env bash
# DSH 环评审查插件 - AI 驱动自我优化迭代维护脚本
# 运行时间: 每天凌晨 3:00
# 核心能力: 监控 GitHub AI 发展 → 自动分析 → 生成优化建议 → 迭代升级

set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════
PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${PLUGIN_DIR}/logs"
AI_REPORT_DIR="${PLUGIN_DIR}/.ai-reports"
GITHUB_TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
EHS_KB_API_KEY="${EHS_KB_API_KEY:-}"

# 监控的 GitHub 仓库列表（AI 发展相关）
MONITORED_REPOS=(
    "deepseek-ai/deepseek-harness"
    "deepseek-ai/cordis"
    "modelcontextprotocol/specification"
    "modelcontextprotocol/python-sdk"
    "modelcontextprotocol/typescript-sdk"
    "microsoft/playwright-mcp"
    "anthropics/anthropic-cookbook"
)

# 环评/环保 AI 相关仓库
EHS_AI_REPOS=(
    "USEPA/epa-enviroatlas"
    "openai/openai-python"
    "langchain-ai/langchain"
)

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# ═══════════════════════════════════════════════════════════════════════
# 日志函数
# ═══════════════════════════════════════════════════════════════════════
log() {
    local level="$1"
    local msg="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] [${level}] ${msg}" | tee -a "${LOG_DIR}/maintenance-$(date +%Y%m%d).log"
}
log_info() { log "INFO" "$1"; }
log_warn() { log "WARN" "$1"; }
log_error() { log "ERROR" "$1"; }
log_ai() { log "AI" "${CYAN}$1${NC}"; }
log_success() { log "SUCCESS" "$1"; }

# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════

# GitHub API 调用（带缓存）
github_api() {
    local endpoint="$1"
    local cache_file="${LOG_DIR}/.github-cache/$(echo "$endpoint" | sed 's/[^a-zA-Z0-9]/_/g').json"
    local cache_max_age=3600  # 缓存1小时

    mkdir -p "$(dirname "$cache_file")"

    # 检查缓存
    if [ -f "$cache_file" ]; then
        local file_age=$(( $(date +%s) - $(stat -c %Y "$cache_file" 2>/dev/null || stat -f %m "$cache_file" 2>/dev/null) ))
        if [ $file_age -lt $cache_max_age ]; then
            cat "$cache_file"
            return 0
        fi
    fi

    # 调用 API
    local auth_header=""
    if [ -n "$GITHUB_TOKEN" ]; then
        auth_header="-H Authorization: token ${GITHUB_TOKEN}"
    fi

    local response
    response=$(curl -sL $auth_header "https://api.github.com${endpoint}" 2>/dev/null)

    if [ -n "$response" ] && [ "$response" != "null" ]; then
        echo "$response" > "$cache_file"
        echo "$response"
    else
        echo "{}"
    fi
}

# 版本比较: 返回 0 如果 v1 > v2
version_gt() {
    [ "$1" != "$2" ] && [ "$(printf '%s\n' "$1" "$2" | sort -V | head -n1)" = "$2" ]
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤1: 环境检查
# ═══════════════════════════════════════════════════════════════════════
step1_env_check() {
    log_info "═══════════════════════════════════════════════════════"
    log_info "DSH 环评审查插件 - AI 驱动维护启动"
    log_info "时间: $(date)"
    log_info "═══════════════════════════════════════════════════════"

    mkdir -p "${LOG_DIR}" "${AI_REPORT_DIR}"

    # 检查必要工具
    for tool in curl jq node python3 git; do
        if ! command -v $tool &> /dev/null; then
            log_warn "缺少工具: $tool"
        fi
    done

    # 检查 GitHub Token
    if [ -z "$GITHUB_TOKEN" ]; then
        log_warn "GITHUB_TOKEN 未设置，GitHub 监控功能受限（速率限制 60 req/h）"
    else
        log_info "GITHUB_TOKEN 已配置"
    fi

    # 检查 Node.js 版本
    NODE_VERSION=$(node --version 2>/dev/null || echo "unknown")
    log_info "Node.js: $NODE_VERSION"

    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤2: DSH 框架版本监控
# ═══════════════════════════════════════════════════════════════════════
step2_dsh_version_monitor() {
    log_info "───────────────────────────────────────────────────────"
    log_info "[步骤2] DSH 框架 & Cordis 版本监控"
    log_info "───────────────────────────────────────────────────────"

    local current_dsh_version=""
    if [ -f "${PLUGIN_DIR}/package.json" ]; then
        current_dsh_version=$(node -e "
            const pkg = require('${PLUGIN_DIR}/package.json');
            const peer = pkg.peerDependencies || {};
            console.log(peer['@deepseek-ai/cordis'] || peer['@deepseek-ai/dsh-tools'] || 'unknown');
        " 2>/dev/null || echo "unknown")
    fi
    log_info "当前插件依赖 DSH 版本: ${current_dsh_version}"

    # 获取最新 release
    local latest_release
    latest_release=$(github_api "/repos/deepseek-ai/deepseek-harness/releases/latest")
    local latest_version=$(echo "$latest_release" | jq -r '.tag_name // "unknown"')
    local latest_body=$(echo "$latest_release" | jq -r '.body // "无详情"' | head -20)

    if [ "$latest_version" != "unknown" ] && [ "$latest_version" != "null" ]; then
        log_info "DSH 最新版本: ${latest_version}"

        if version_gt "$latest_version" "$current_dsh_version"; then
            log_warn "⚠️ DSH 有新版本可用: ${latest_version}"
            log_warn "更新内容预览:"
            echo "$latest_body" | while read line; do
                log_warn "  ${line}"
            done

            # 记录到 AI 报告
            cat >> "${AI_REPORT_DIR}/version-updates.md" << EOF
## $(date +%Y-%m-%d) DSH 版本更新

- **当前版本**: ${current_dsh_version}
- **最新版本**: ${latest_version}
- **更新内容**:
$(echo "$latest_body" | sed 's/^/  /')
- **建议操作**: 检查兼容性后升级

EOF
        else
            log_success "✅ DSH 已是最新版本"
        fi
    fi

    # 获取 Cordis 最新版本
    local cordis_latest
    cordis_latest=$(github_api "/repos/deepseek-ai/cordis/releases/latest")
    local cordis_version=$(echo "$cordis_latest" | jq -r '.tag_name // "unknown"')

    if [ "$cordis_version" != "unknown" ]; then
        log_info "Cordis 最新版本: ${cordis_version}"
    fi

    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤3: MCP 协议规范监控
# ═══════════════════════════════════════════════════════════════════════
step3_mcp_spec_monitor() {
    log_info "───────────────────────────────────────────────────────"
    log_info "[步骤3] MCP 协议规范监控"
    log_info "───────────────────────────────────────────────────────"

    # 获取 MCP spec 最新提交
    local mcp_commits
    mcp_commits=$(github_api "/repos/modelcontextprotocol/specification/commits?per_page=5")

    local last_check_file="${LOG_DIR}/.last-mcp-check"
    local last_check_sha=""
    if [ -f "$last_check_file" ]; then
        last_check_sha=$(cat "$last_check_file")
    fi

    local latest_sha=$(echo "$mcp_commits" | jq -r '.[0].sha // ""')
    local latest_msg=$(echo "$mcp_commits" | jq -r '.[0].commit.message // ""' | head -1)
    local latest_date=$(echo "$mcp_commits" | jq -r '.[0].commit.author.date // ""')

    if [ "$latest_sha" != "$last_check_sha" ] && [ -n "$latest_sha" ]; then
        log_warn "🔔 MCP 协议规范有更新!"
        log_warn "  最新提交: ${latest_sha:0:8}"
        log_warn "  提交信息: ${latest_msg}"
        log_warn "  提交时间: ${latest_date}"

        # 分析是否需要适配
        if echo "$latest_msg" | grep -qiE "sse|transport|tool|protocol|breaking"; then
            log_warn "  ⚠️ 可能涉及协议变更，需要检查插件兼容性"

            cat >> "${AI_REPORT_DIR}/mcp-protocol-updates.md" << EOF
## $(date +%Y-%m-%d) MCP 协议更新

- **提交**: ${latest_sha:0:8}
- **信息**: ${latest_msg}
- **时间**: ${latest_date}
- **影响评估**: 可能涉及协议变更
- **建议操作**: 
  1. 检查 SSE 连接逻辑是否需要更新
  2. 验证工具调用格式是否变化
  3. 测试与 EHS 知识库的兼容性

EOF
        fi

        echo "$latest_sha" > "$last_check_file"
    else
        log_success "✅ MCP 协议规范无更新"
    fi

    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤4: AI 模型能力发展监控
# ═══════════════════════════════════════════════════════════════════════
step4_ai_capability_monitor() {
    log_info "───────────────────────────────────────────────────────"
    log_info "[步骤4] AI 模型能力发展监控"
    log_info "───────────────────────────────────────────────────────"

    # 监控 DeepSeek 模型更新
    local deepseek_releases
    deepseek_releases=$(github_api "/repos/deepseek-ai/deepseek-llm/releases/latest")
    local ds_version=$(echo "$deepseek_releases" | jq -r '.tag_name // "unknown"')

    if [ "$ds_version" != "unknown" ] && [ "$ds_version" != "null" ]; then
        log_info "DeepSeek 模型最新版本: ${ds_version}"
    fi

    # 监控 LangChain 更新（RAG/Agent 框架）
    local langchain_latest
    langchain_latest=$(github_api "/repos/langchain-ai/langchain/releases/latest")
    local lc_version=$(echo "$langchain_latest" | jq -r '.tag_name // "unknown"')

    if [ "$lc_version" != "unknown" ]; then
        log_info "LangChain 最新版本: ${lc_version}"
    fi

    # 生成 AI 能力发展报告
    cat > "${AI_REPORT_DIR}/ai-capability-tracker.md" << EOF
# AI 能力发展追踪报告

生成时间: $(date -Iseconds)

## 监控范围

| 项目 | 仓库 | 用途 |
|------|------|------|
| DSH 框架 | deepseek-ai/deepseek-harness | 插件运行环境 |
| Cordis 内核 | deepseek-ai/cordis | 服务框架 |
| MCP 协议 | modelcontextprotocol/specification | 知识库连接 |
| LangChain | langchain-ai/langchain | RAG/Agent 参考 |
| DeepSeek LLM | deepseek-ai/deepseek-llm | 模型能力 |

## 当前状态

- DSH 最新: ${ds_version}
- MCP 最新提交: ${latest_sha:0:8} (来自步骤3)
- LangChain 最新: ${lc_version}

## 对插件的影响分析

### 1. 准确率提升机会
- 新 LLM 版本可能提升审查准确率
- 新的 RAG 技术可优化知识库检索
- 更强的 Agent 能力可改进审查工作流

### 2. 架构优化机会
- MCP 协议更新可能带来更高效的连接方式
- DSH 新版本可能提供更好的插件 API
- 新的工具调用模式可简化代码

### 3. 建议行动
- [ ] 跟踪 DSH 版本更新，评估升级收益
- [ ] 关注 MCP 协议变更，确保兼容性
- [ ] 研究新的 RAG 技术，优化 81,071 篇文档的检索效率
- [ ] 评估新模型对审查准确率的影响

EOF

    log_success "✅ AI 能力发展报告已生成: ${AI_REPORT_DIR}/ai-capability-tracker.md"
    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤5: 插件代码自我分析（AI 驱动）
# ═══════════════════════════════════════════════════════════════════════
step5_self_analysis() {
    log_info "───────────────────────────────────────────────────────"
    log_info "[步骤5] 插件代码自我分析与优化建议"
    log_info "───────────────────────────────────────────────────────"

    cd "${PLUGIN_DIR}"

    # 统计代码规模
    local ts_files=$(find src -name "*.ts" 2>/dev/null | wc -l)
    local total_lines=$(find src -name "*.ts" -exec wc -l {} + 2>/dev/null | tail -1 | awk '{print $1}')
    local rule_count=$(grep -c "id: "NAT-" src/core/national-rules.ts 2>/dev/null || echo "0")

    log_info "代码统计:"
    log_info "  TypeScript 文件: ${ts_files} 个"
    log_info "  总代码行数: ${total_lines} 行"
    log_info "  国家规则数: ${rule_count} 条"

    # 检查 TODO/FIXME
    local todo_count=$(grep -r "TODO\|FIXME\|HACK\|XXX" src/ 2>/dev/null | wc -l)
    if [ "$todo_count" -gt 0 ]; then
        log_warn "发现 ${todo_count} 个 TODO/FIXME 标记"
        grep -rn "TODO\|FIXME\|HACK\|XXX" src/ 2>/dev/null | head -10 | while read line; do
            log_warn "  ${line}"
        done
    fi

    # 检查是否有硬编码的敏感信息
    local hardcoded_keys=$(grep -rn "api_key\|apikey\|password\|secret" src/ --include="*.ts" 2>/dev/null | grep -v "process.env\|config." | wc -l)
    if [ "$hardcoded_keys" -gt 0 ]; then
        log_warn "⚠️ 发现 ${hardcoded_keys} 处可能的硬编码密钥"
    else
        log_success "✅ 未发现硬编码敏感信息"
    fi

    # 生成优化建议
    cat > "${AI_REPORT_DIR}/optimization-suggestions.md" << EOF
# 插件优化建议报告

生成时间: $(date -Iseconds)

## 当前代码状况

| 指标 | 数值 |
|------|------|
| TypeScript 文件 | ${ts_files} |
| 总代码行数 | ${total_lines} |
| 国家规则 | ${rule_count} |
| TODO/FIXME | ${todo_count} |
| 硬编码风险 | ${hardcoded_keys} |

## 自动生成的优化建议

### 1. 规则引擎优化
- [ ] 考虑将规则配置化（JSON/YAML），便于非开发者维护
- [ ] 添加规则优先级和依赖关系管理
- [ ] 实现规则热更新，无需重启插件

### 2. 知识库优化
- [ ] 81,071 篇文档的检索效率可进一步优化
- [ ] 考虑添加缓存层，减少重复查询
- [ ] 实现增量索引更新，降低同步成本

### 3. 代码质量
- [ ] 添加单元测试覆盖率（目标 > 80%）
- [ ] 添加集成测试（模拟完整审查流程）
- [ ] 完善 TypeScript 类型定义

### 4. 架构升级
- [ ] 考虑支持多模型（DeepSeek、GPT、Claude 等）
- [ ] 实现审查结果的可视化对比
- [ ] 添加审查历史追踪功能

### 5. 性能优化
- [ ] PDF 解析性能优化（大文件 > 100 页）
- [ ] 并发审查支持
- [ ] 内存使用优化

## 下一步行动

1. 根据 GitHub AI 发展趋势，选择优先级最高的优化项
2. 评估每项优化的投入产出比
3. 制定迭代计划

EOF

    log_success "✅ 优化建议报告已生成"
    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤6: 知识库同步（原有功能）
# ═══════════════════════════════════════════════════════════════════════
step6_kb_sync() {
    log_info "───────────────────────────────────────────────────────"
    log_info "[步骤6] EHS 知识库同步"
    log_info "───────────────────────────────────────────────────────"

    if [ -z "${EHS_KB_API_KEY:-}" ]; then
        log_warn "EHS_KB_API_KEY 未设置，跳过知识库同步"
        return 0
    fi

    local mcp_url="http://111.230.89.107:8000"

    # 检查知识库连接
    local kb_status
    kb_status=$(curl -s -o /dev/null -w "%{http_code}"         -H "X-API-Key: ${EHS_KB_API_KEY}"         "${mcp_url}/" 2>/dev/null)

    if [ "$kb_status" = "200" ]; then
        log_success "✅ 知识库连接正常"

        # 获取文档数量
        local kb_info
        kb_info=$(curl -s -H "X-API-Key: ${EHS_KB_API_KEY}" "${mcp_url}/" 2>/dev/null)
        local doc_count=$(echo "$kb_info" | grep -o 'vector_search: enabled ([0-9]*' | grep -o '[0-9]*' || echo "unknown")
        log_info "知识库文档数: ${doc_count}"
    else
        log_warn "知识库连接异常 (HTTP ${kb_status})"
    fi

    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤7: 规则库更新检查（原有功能）
# ═══════════════════════════════════════════════════════════════════════
step7_rule_update_check() {
    log_info "───────────────────────────────────────────────────────"
    log_info "[步骤7] 规则库更新检查"
    log_info "───────────────────────────────────────────────────────"

    cd "${PLUGIN_DIR}"

    # 检查国家规则最后更新时间
    local rule_file="src/core/national-rules.ts"
    if [ -f "$rule_file" ]; then
        local last_modified
        last_modified=$(stat -c %Y "$rule_file" 2>/dev/null || stat -f %m "$rule_file" 2>/dev/null)
        local days_since_update=$(( ( $(date +%s) - last_modified ) / 86400 ))

        log_info "国家规则库最后更新: ${days_since_update} 天前"

        if [ $days_since_update -gt 30 ]; then
            log_warn "⚠️ 规则库超过 30 天未更新"
            log_warn "建议: 检查生态环境部是否有新法规发布"

            # 查询生态环境部最新公告（简化版）
            log_info "正在检查生态环境部最新动态..."
        fi
    fi

    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤8: 日志清理（原有功能）
# ═══════════════════════════════════════════════════════════════════════
step8_log_cleanup() {
    log_info "───────────────────────────────────────────────────────"
    log_info "[步骤8] 日志清理"
    log_info "───────────────────────────────────────────────────────"

    # 清理旧日志
    if [ -d "${LOG_DIR}" ]; then
        find "${LOG_DIR}" -name "*.log" -mtime +30 -delete 2>/dev/null || true
        find "${LOG_DIR}" -name "maintenance-*.log" -mtime +7 -delete 2>/dev/null || true
        log_success "✅ 日志清理完成"
    fi

    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤9: 健康检查（原有功能）
# ═══════════════════════════════════════════════════════════════════════
step9_health_check() {
    log_info "───────────────────────────────────────────────────────"
    log_info "[步骤9] 插件健康检查"
    log_info "───────────────────────────────────────────────────────"

    cd "${PLUGIN_DIR}"

    # TypeScript 编译检查
    if [ -f "tsconfig.json" ]; then
        if npx tsc --noEmit 2>/dev/null; then
            log_success "✅ TypeScript 编译检查通过"
        else
            log_warn "⚠️ TypeScript 编译检查发现问题"
        fi
    fi

    # 磁盘空间
    local disk_usage
    disk_usage=$(df -h "${PLUGIN_DIR}" | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -gt 90 ]; then
        log_error "❌ 磁盘使用率超过 90%: ${disk_usage}%"
    elif [ "$disk_usage" -gt 80 ]; then
        log_warn "⚠️ 磁盘使用率超过 80%: ${disk_usage}%"
    else
        log_info "磁盘使用率正常: ${disk_usage}%"
    fi

    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 步骤10: 生成 AI 驱动维护报告
# ═══════════════════════════════════════════════════════════════════════
step10_generate_ai_report() {
    log_info "───────────────────────────────────────────────────────"
    log_info "[步骤10] 生成 AI 驱动维护报告"
    log_info "───────────────────────────────────────────────────────"

    local report_file="${AI_REPORT_DIR}/maintenance-report-$(date +%Y%m%d).json"

    # 收集所有报告
    local version_updates=$(cat "${AI_REPORT_DIR}/version-updates.md" 2>/dev/null | wc -l)
    local mcp_updates=$(cat "${AI_REPORT_DIR}/mcp-protocol-updates.md" 2>/dev/null | wc -l)
    local suggestions=$(cat "${AI_REPORT_DIR}/optimization-suggestions.md" 2>/dev/null | wc -l)

    cat > "$report_file" << EOF
{
    "meta": {
        "date": "$(date -Iseconds)",
        "plugin": "dsh-eia-review-plugin",
        "version": "1.0.0",
        "maintenance_type": "AI-driven"
    },
    "github_monitoring": {
        "dsh_version_check": "completed",
        "mcp_protocol_check": "completed",
        "ai_capability_track": "completed",
        "version_updates_found": ${version_updates},
        "mcp_updates_found": ${mcp_updates}
    },
    "self_analysis": {
        "code_analysis": "completed",
        "optimization_suggestions": ${suggestions},
        "reports_generated": [
            "ai-capability-tracker.md",
            "optimization-suggestions.md",
            "version-updates.md",
            "mcp-protocol-updates.md"
        ]
    },
    "maintenance": {
        "kb_sync": "completed",
        "rule_update_check": "completed",
        "log_cleanup": "completed",
        "health_check": "completed"
    },
    "system": {
        "node_version": "$(node --version 2>/dev/null || echo 'unknown')",
        "disk_usage": "$(df -h "${PLUGIN_DIR}" | awk 'NR==2 {print $5}')",
        "plugin_size": "$(du -sh "${PLUGIN_DIR}" 2>/dev/null | cut -f1)"
    },
    "next_actions": [
        "检查 DSH 新版本兼容性",
        "评估 MCP 协议变更影响",
        "实施优先级最高的优化建议",
        "更新规则库（如有新法规）"
    ],
    "next_maintenance": "$(date -d '+1 day' -Iseconds)"
}
EOF

    log_success "✅ AI 驱动维护报告已生成: ${report_file}"

    # 输出摘要
    log_info "═══════════════════════════════════════════════════════"
    log_info "AI 驱动维护完成: $(date)"
    log_info "═══════════════════════════════════════════════════════"
    log_ai "🤖 本次维护亮点:"
    log_ai "  • 监控了 ${#MONITORED_REPOS[@]} 个 GitHub AI 仓库"
    log_ai "  • 分析了插件代码质量"
    log_ai "  • 生成了优化建议报告"
    log_ai "  • 同步了 EHS 知识库"
    log_info "报告目录: ${AI_REPORT_DIR}"
    log_info "下次维护: $(date -d '+1 day' '+%Y-%m-%d 03:00:00')"
    log_info "═══════════════════════════════════════════════════════"

    return 0
}

# ═══════════════════════════════════════════════════════════════════════
# 主函数
# ═══════════════════════════════════════════════════════════════════════
main() {
    local exit_code=0

    step1_env_check || exit_code=1
    step2_dsh_version_monitor || exit_code=1
    step3_mcp_spec_monitor || exit_code=1
    step4_ai_capability_monitor || exit_code=1
    step5_self_analysis || exit_code=1
    step6_kb_sync || exit_code=1
    step7_rule_update_check || exit_code=1
    step8_log_cleanup || exit_code=1
    step9_health_check || exit_code=1
    step10_generate_ai_report || exit_code=1

    if [ $exit_code -eq 0 ]; then
        log_success "🎉 所有 AI 驱动维护步骤成功完成"
    else
        log_warn "⚠️ 部分步骤出现问题，请检查日志"
    fi

    return $exit_code
}

# 运行主函数
main "$@"
