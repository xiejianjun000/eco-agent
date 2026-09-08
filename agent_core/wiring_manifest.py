"""
wiring_manifest.py — 接线清单（单一权威源）

聊天通道必须暴露的工具白名单：新增/下线聊天工具必须先改这里，
test_tool_wiring 回归测试保证清单与现实一致——防止"注册了但没接线"
类缺口（如 query_air_quality 曾长期缺失）。
"""

WIRED_REQUIRED: list[str] = [
    # 法规与知识
    "statute_lookup",
    "statute_search",
    "kb_search",
    "kb_semantic_search",
    # 计算与沙箱
    "execute_code",
    "calculate_carbon_emission",
    # 网络
    "web_fetch",
    "open_url",
    # 环境数据
    "query_air_quality",
    # 文书与文档
    "save_document",
    "analyze_document",
    "generate_pptx",
    "hunan_case_list",
    # 提示词状态机（DSH 式模块化提示词）
    "switch_persona",
    "audit_tail",
    "session_log_tail",
    # 执行层（结构性差距补齐 1-5）
    "shell_run",
    "file_read",
    "file_write",
    "file_edit",
    "web_search",
    "spawn_goal",
    "goal_status",
    "system_reload",
    "statute_related",
    # 腾讯文档 HTML 一键上云（aipage 打包 + COS 上传 + 导入管线）
    "tdocs_upload_html",
]

# 通道级分发工具：实现不在 tools_registry._HANDLERS，而在 server/api/chat.py
# 自身（web_fetch、generate_pptx 惰性挂 docgen 插件）或经 MCP 远程注册（kb_*）。
CHANNEL_DISPATCHED: list[str] = [
    # 成果统一呈现入口（对标 WorkBuddy present_files）：
    # 只校验文件存在并回传元信息，由 chat.py 内部分派，无独立 handler。
    "present_files",
    # 按需加载 SKILL.md（对标 WorkBuddy use_skill），chat.py 内部分派
    "use_skill",
    "web_fetch",
    "open_url",
    "generate_pptx",
    "kb_search",
    "kb_semantic_search",
    "hunan_case_list",
    "switch_persona",
    "audit_tail",
    "session_log_tail",
    "shell_run",
    "file_read",
    "file_write",
    "file_edit",
    "web_search",
    "spawn_goal",
    "goal_status",
    "system_reload",
    "statute_related",
    "tdocs_upload_html",
    "chart_render",
    # cron 定时调度（handler 在 chat.py _run_tool 的 cron_* 分支）
    "cron_add",
    "cron_list",
    "cron_remove",
    "cron_run",
    # 记忆树/策略热更新工具（handler 在 chat.py _run_tool 的 eco_memory_* 分支）
    "eco_memory_add",
    "eco_memory_update",
    "eco_memory_delete",
    "eco_memory_search",
    "eco_memory_stats",
    "eco_memory_prune",
    "eco_memory_sync",
    "eco_policy_reload",
    # 三层穿透取证工具（handler 在 chat.py _run_tool 的 grep/glob/api_probe/inspect 分支）
    "grep",
    "glob",
    "api_probe",
    "inspect",
]
