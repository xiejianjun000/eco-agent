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
    "water_station_realtime",
    "air_forecast",
    "hunan_env_monthly_report",
    # 腾讯文档 HTML 一键上云（aipage 打包 + COS 上传 + 导入管线）
    "tdocs_upload_html",
    # 政务平台-污染源在线监测（娄底市重点污染源自动监控，govmcp 格式挂载）
    "wryzxjc_list_regions",
    "wryzxjc_list_pollution_sources",
    "wryzxjc_get_pollution_source",
    "wryzxjc_list_alarms",
    "wryzxjc_list_devices",
    "wryzxjc_list_realtime_data",
    "wryzxjc_list_jcd_tree",
    "wryzxjc_list_history_data",
    # 政务平台-国家四平台（综合执法监管，govmcp 格式挂载）
    "sthjzf_query_view",
    "sthjzf_get_menu",
    "sthjzf_get_view_config",
    "sthjzf_query_cases",
    "sthjzf_list_depts",
    "sthjzf_query_case_detail",
    "sthjzf_query_case_statistics",
    "sthjzf_water_current_user",
    "sthjzf_water_task_statistics",
    "sthjzf_water_task_list",
    "sthjzf_water_supervise_statistics",
    # 政务平台-排污许可管理（全国排污许可证管理信息平台-管理端，govmcp 格式挂载）
    "permit_menu",
    "permit_license_list",
    "permit_enterprise_list",
    "permit_jgzf_menu",
    "permit_jgzf_license_execution",
    "permit_jgzf_stop_production",
    "permit_jgzf_enterprise_archive",
    "permit_area_list",
    "permit_industry_list",
]

# 通道级分发工具：实现不在 tools_registry._HANDLERS，而在 server/api/chat.py
# 自身（web_fetch、generate_pptx 惰性挂 docgen 插件）或经 MCP 远程注册（kb_*）。
CHANNEL_DISPATCHED: list[str] = [
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
    "water_station_realtime",
    "air_forecast",
    "hunan_env_monthly_report",
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
]
