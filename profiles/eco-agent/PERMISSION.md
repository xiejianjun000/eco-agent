# PERMISSION.md — ECO AGENT 工具权限配置

> **基于 OpenWorker Risk Model 的 4 级风险权限体系**
> 版本：v0.1.0

---

## 风险等级定义

| 等级 | 标签 | 定义 | 审批要求 |
|:----:|:-----|:-----|:---------|
| **L1** | READ | 只读操作，无副作用 | 自动允许 |
| **L2** | WRITE_LOCAL | 在安全区域内创建/修改文件 | 自动允许 |
| **L3** | EXEC | 执行命令/脚本 | 路径白名单内自动允许，其余审批 |
| **L4** | EXTERNAL | 网络请求/外部服务调用 | 必须人工审批 |

---

## 工具权限清单

### L1 — READ（只读）

```yaml
allow:
  - path: "~/.eco/profiles/eco-agent/**"
    reason: "Profile 目录内的配置读取"
  - path: "~/.eco/workspace/**"
    reason: "项目文件读取"
  - path: "~/Documents/Obsidian Vault/raw/**"
    reason: "知识原文只读检索"
  - path: "~/Documents/Obsidian Vault/wiki/**"
    reason: "知识知识只读检索"
  - mcp_tools:
      - eco-knowledge/search
      - eco-knowledge/retrieve
      - obsidian-vault/search
      - obsidian-vault/read
  - web_search: true
  - web_fetch: true
```

### L2 — WRITE_LOCAL（本地写入）

```yaml
allow:
  - path: "~/.eco/memory-tree/**"
    reason: "Memory Tree 节点写入"
  - path: "~/.eco/.memory/**"
    reason: "审计日志写入"
  - path: "~/.eco/skills/**"
    reason: "技能文件写入（技能孵化）"
  - path: "~/.eco/CHANGELOG.md"
    reason: "版本历史更新"
  - path: "~/.eco/scripts/**"
    reason: "自动化脚本写入"

deny:
  - path: "~/Documents/Obsidian Vault/raw/**"
    reason: "原文只读，禁止修改"
  - path: "~/Documents/Obsidian Vault/wiki/**"
    reason: "知识只读，禁止修改"
  - path: "**/.env"
    reason: "环境变量文件，禁止读取或修改"
  - path: "**/*.key"
  - path: "**/*.pem"
```

### L3 — EXEC（命令执行）

```yaml
allow_auto:
  - command: "python _scripts/lint.py"
    reason: "健康检查脚本"
  - command: "python _scripts/quality_audit.py"
    reason: "质量审计脚本"
  - command: "git *"
    reason: "Git 操作（版本管理）"
  - command: "pip install *"
    reason: "Python 依赖安装"

require_approval:
  - command: "rm -rf *"
    reason: "高危删除操作"
  - command: "chmod *"
    reason: "权限修改操作"
  - command: "sudo *"
    reason: "提权操作"
  - command: "> *"
    reason: "重定向写入（谨慎使用）"
```

### L4 — EXTERNAL（外部网络）

```yaml
require_approval:
  - api: "any"
    reason: "所有外部 API 调用必须审批（MVP 阶段）"
```

---

## 审批流程

```
用户请求 → 风险等级判定
  ├── L1 → 自动执行
  ├── L2 → 自动执行
  ├── L3 (白名单内) → 自动执行
  ├── L3 (白名单外) → 挂起审批收件箱 → 用户审核 → 执行/拒绝
  └── L4 → 挂起审批收件箱 → 用户审核 → 执行/拒绝
```

---

## 风险等级快速判定表

| 操作示例 | 等级 | 自动/审批 |
|:---------|:----:|:---------:|
| 查询知识条文 | L1 | 自动 |
| 检索相似案例 | L1 | 自动 |
| 写入 Memory Tree | L2 | 自动 |
| 运行质量审计 | L3 | 自动（白名单） |
| 安装新 Python 包 | L3 | 自动（白名单） |
| 删除文件 | L3 | 审批 |
| 调用外部 API | L4 | 审批 |
| 联网下载文件 | L4 | 审批 |

---

## 工具风险覆盖（运行时生效）

`agent_core/permissions.py` 按工具名前缀判定默认风险级；以下 `tool_risk_overrides`
块可逐工具覆盖（增删条目后重启会话生效，全部决策写 SM3 审计链 source=permission）：

```yaml
# MCP 法规知识库（eco_kb）五个只读检索工具：L1 自动放行
tool_risk_overrides:
  - tool: execute_code
    level: L3
  - tool: generate_approval_document
    level: L4
  - tool: mcp__eco_kb__eco_search
    level: L1
  - tool: mcp__eco_kb__eco_retrieve
    level: L1
  - tool: mcp__eco_kb__eco_statute_query
    level: L1
  - tool: mcp__ehs_kb__kb_search
    level: L1
  - tool: mcp__ehs_kb__kb_read
    level: L1
  - tool: mcp__ehs_kb__kb_list
    level: L1
  - tool: mcp__ehs_kb__kb_status
    level: L1
  - tool: mcp__ehs_kb__kb_semantic_search
    level: L1
  - tool: mcp__eco_kb__eco_graph_query
    level: L1
  - tool: mcp__eco_kb__eco_list_statutes
    level: L1
  - tool: mcp__eia__kb_search
    level: L1
  - tool: mcp__eia__kb_verify
    level: L1
  - tool: mcp__eia__kb_calculate
    level: L1
  - tool: mcp__eia__kb_industry_info
    level: L1
  - tool: mcp__github__search_repositories
    level: L1
  - tool: mcp__github__get_file_contents
    level: L1
  - tool: mcp__github__list_commits
    level: L1
  - tool: mcp__github__list_issues
    level: L1
  - tool: mcp__github__get_issue
    level: L1
  - tool: mcp__github__search_code
    level: L1
  - tool: mcp__github__search_issues
    level: L1
  - tool: mcp__github__search_users
    level: L1
  - tool: mcp__github__get_me
    level: L1
  - tool: mcp__github__list_branches
    level: L1
  - tool: mcp__permit__search_licenses
    level: L1
  - tool: mcp__permit__get_license_detail
    level: L1
  - tool: mcp__permit__get_license_pages
    level: L1
  - tool: mcp__permit__download_license_page
    level: L1
  - tool: mcp__permit__get_qrcode_info
    level: L1
  - tool: mcp__permit__get_post_permit_status
    level: L1
  - tool: mcp__permit__get_rectification
    level: L1
  - tool: mcp__permit__get_announcements
    level: L1
  - tool: mcp__permit__list_policy_docs
    level: L1
  - tool: mcp__permit__get_policy_detail
    level: L1
  - tool: mcp__permit__get_discharge_points
    level: L1
  - tool: mcp__permit__get_monitoring_data
    level: L1
  - tool: mcp__mee_kb__read_web_page
    level: L1
  - tool: mcp__mee_kb__list_web_links
    level: L1
  - tool: mcp__mee_kb__read_air_quality
    level: L1
  - tool: mcp__mee_kb__read_air_forecast
    level: L1
  - tool: mcp__mee_kb__read_air_monthly
    level: L1
  - tool: mcp__mee_kb__read_surface_water
    level: L1
  - tool: mcp__mee_kb__read_sea_water
    level: L1
  - tool: mcp__mee_kb__read_radiation_level
    level: L1
  - tool: mcp__mee_kb__list_mee_categories
    level: L1
  - tool: mcp__mee_kb__read_mee_list
    level: L1
  - tool: mcp__mee_kb__read_mee_article
    level: L1
  - tool: mcp__mee_kb__list_policy_types
    level: L1
  - tool: mcp__mee_kb__read_policy_type
    level: L1
  - tool: mcp__mee_kb__read_policy_interpretation
    level: L1
  - tool: mcp__mee_kb__list_quality_reports
    level: L1
  - tool: mcp__mee_kb__read_quality_report
    level: L1
  - tool: mcp__mee_kb__list_interact_sections
    level: L1
  - tool: mcp__mee_kb__read_interact
    level: L1
  - tool: mcp__mee_kb__read_exposure
    level: L1
  - tool: mcp__mee_kb__read_english_list
    level: L1
  - tool: mcp__mee_kb__list_nnsa_sections
    level: L1
  - tool: mcp__mee_kb__read_nnsa_list
    level: L1
  - tool: mcp__mee_kb__search_site
    level: L1
  - tool: mcp__mee_kb__search_policy
    level: L1
  - tool: mcp__mee_kb__read_policy
    level: L1
  - tool: mcp__mee_kb__search_standard
    level: L1
  - tool: mcp__mee_kb__read_standard
    level: L1
  - tool: mcp__mee_kb__query_eia_credit
    level: L1
  - tool: mcp__mee_kb__search_permit
    level: L1
  - tool: mcp__mee_kb__search_waste_category
    level: L1
  - tool: mcp__mee_kb__list_domains_meta
    level: L1
  - tool: mcp__mee_kb__list_agencies
    level: L1
  - tool: mcp__mee_kb__list_river_bureaus
    level: L1
  - tool: mcp__mee_kb__list_nuclear_entrances
    level: L1
  - tool: mcp__mee_kb__list_eia_entrances
    level: L1
  - tool: mcp__mee_kb__list_waste_entrances
    level: L1
  - tool: mcp__mee_kb__list_laws
    level: L1
  - tool: mcp__mee_kb__list_standard_categories
    level: L1
  - tool: mcp__mee_kb__permit_guide
    level: L1
  - tool: mcp__mee_kb__rag_query
    level: L1
  - tool: mcp__mee_kb__rag_ingest
    level: L1
  - tool: mcp__mee_kb__download_file
    level: L1
  - tool: mcp__mee_kb__download_standard_pdf
    level: L1
  - tool: mcp__mee_kb__export_mee_list
    level: L1
  - tool: mcp__mee_kb__export_air_quality_csv
    level: L1
  - tool: mcp__mee_kb__list_downloads
    level: L1
  - tool: mcp__hunan_env__air_quality_realtime
    level: L1
  - tool: mcp__hunan_env__air_quality_hourly
    level: L1
  - tool: mcp__hunan_env__air_quality_forecast
    level: L1
  - tool: mcp__hunan_env__air_quality_rank_daily
    level: L1
  - tool: mcp__hunan_env__eia_publicity_search
    level: L1
  - tool: mcp__hunan_env__policy_document_search
    level: L1
  - tool: mcp__hunan_env__notice_announcement_list
    level: L1
  - tool: mcp__hunan_env__environmental_quality_monthly
    level: L1
  - tool: mcp__hunan_env__env_statistics_report
    level: L1
  - tool: mcp__hunan_env__enforcement_case_search
    level: L1
  - tool: mcp__hunan_env__credit_evaluation_query
    level: L1
  - tool: mcp__hunan_env__news_dynamic_list
    level: L1
  - tool: mcp__hunan_env__interaction_list
    level: L1
  - tool: mcp__hunan_env__key_domain_list
    level: L1
  - tool: mcp__hunan_env__legal_document_list
    level: L1
  - tool: mcp__hunan_env__management_public_list
    level: L1
  - tool: mcp__hunan_env__org_structure_list
    level: L1
  - tool: mcp__hunan_env__media_center_list
    level: L1
  - tool: mcp__hunan_env__document_detail
    level: L1
  - tool: mcp__hunan_env__site_search
    level: L1
  - tool: hunan_case_list
    level: L2
  # 政务平台-污染源在线监测（govmcp 只读，L1 自动放行；本机直连 218.77.102.213）
  - tool: wryzxjc_list_regions
    level: L1
  - tool: wryzxjc_list_pollution_sources
    level: L4
  - tool: wryzxjc_get_pollution_source
    level: L4
  - tool: wryzxjc_list_alarms
    level: L4
  - tool: wryzxjc_list_devices
    level: L4
  - tool: wryzxjc_list_realtime_data
    level: L4
  - tool: wryzxjc_list_jcd_tree
    level: L4
  - tool: wryzxjc_list_history_data
    level: L4
  # 政务平台-国家四平台（govmcp 只读，L1 自动放行；CAS sthjzf.lem.org.cn）
  - tool: sthjzf_query_view
    level: L1
  - tool: sthjzf_get_menu
    level: L1
  - tool: sthjzf_get_view_config
    level: L1
  - tool: sthjzf_query_cases
    level: L4
  - tool: sthjzf_list_depts
    level: L1
  - tool: sthjzf_query_case_detail
    level: L4
  - tool: sthjzf_query_case_statistics
    level: L4
  - tool: sthjzf_water_current_user
    level: L4
  - tool: sthjzf_water_task_statistics
    level: L4
  - tool: sthjzf_water_task_list
    level: L4
  - tool: sthjzf_water_supervise_statistics
    level: L4
  # 政务平台-排污许可管理（govmcp 只读，L1 自动放行；内网 PERMIT_BASE）
  - tool: permit_menu
    level: L1
  - tool: permit_license_list
    level: L4
  - tool: permit_enterprise_list
    level: L4
  - tool: permit_jgzf_menu
    level: L4
  - tool: permit_jgzf_license_execution
    level: L4
  - tool: permit_jgzf_stop_production
    level: L4
  - tool: permit_jgzf_enterprise_archive
    level: L4
  - tool: permit_area_list
    level: L1
  - tool: permit_industry_list
    level: L1
  # 写入类工具：审批闸门 + confirm 双保险（不进聊天工具表）
  - tool: sthjzf_water_clue_verify
    level: L4
  - tool: sthjzf_water_clue_confirm
    level: L4
  # 执法阶段人设切换（提示词状态机，可逆 + SM3 审计）
  - tool: switch_persona
    level: L1
  # 本机浏览器打开（用户可见可关可逆，白名单域名）
  - tool: open_url
    level: L2
  # SM3 审计链回溯（只读自证）
  - tool: audit_tail
    level: L1
  # 事件溯源会话日志回溯（只读自证）
  - tool: session_log_tail
    level: L1
  # 执行层（结构性差距补齐：shell 白名单 / 文件精确编辑 / 搜索 / 长任务目标）
  - tool: shell_run
    level: L3
  - tool: file_read
    level: L1
  - tool: file_write
    level: L2
  - tool: file_edit
    level: L2
  - tool: web_search
    level: L1
  - tool: spawn_goal
    level: L2
  - tool: goal_status
    level: L1
  # 挂载自闭环：改 .env 后热重载（重读环境+重连 MCP，免重启进程）
  - tool: system_reload
    level: L2
  - tool: statute_related
    level: L1
  - tool: water_station_realtime
    level: L1
  - tool: air_forecast
    level: L1
  - tool: hunan_env_monthly_report
    level: L1
  # 腾讯文档官方 MCP（读 L1 自动放行；建文档 L2 自动放行；删除/权限类默认 L3+ 不豁免）
  - tool: mcp__tencent_docs__get_content
    level: L1
  - tool: mcp__tencent_docs__manage_search_file
    level: L1
  - tool: mcp__tencent_docs__query_space_list
    level: L1
  - tool: mcp__tencent_docs__manage_create_file
    level: L2
  - tool: mcp__tencent_docs__doc_create_with_markdown
    level: L2
  - tool: mcp__tencent_docs__create_space_node
    level: L2
  - tool: mcp__tencent_docs__create_space
    level: L2
  # 腾讯文档 HTML 一键上云（aipage 打包 + COS 上传 + 导入管线，L2 本地写入自动放行）
  - tool: tdocs_upload_html
    level: L2

  # 高德地图 GIS MCP（eco-gis-amap，L1 只读/本地空间计算：地址↔经纬度/POI/路线/静态图/空间分析）
  - tool: mcp__eco-gis-amap__amap_key_diagnose
    level: L1
  - tool: mcp__eco-gis-amap__amap_geocode
    level: L1
  - tool: mcp__eco-gis-amap__amap_regeocode
    level: L1
  - tool: mcp__eco-gis-amap__amap_search_poi
    level: L1
  - tool: mcp__eco-gis-amap__amap_inputtips
    level: L1
  - tool: mcp__eco-gis-amap__amap_district
    level: L1
  - tool: mcp__eco-gis-amap__amap_weather
    level: L1
  - tool: mcp__eco-gis-amap__amap_ip_location
    level: L1
  - tool: mcp__eco-gis-amap__amap_route
    level: L1
  - tool: mcp__eco-gis-amap__amap_distance
    level: L1
  - tool: mcp__eco-gis-amap__amap_static_map
    level: L1
  - tool: mcp__eco-gis-amap__amap_coordinate_convert
    level: L1
  - tool: mcp__eco-gis-amap__amap_grasp_road
    level: L1
  - tool: mcp__eco-gis-amap__spatial_buffer
    level: L1
  - tool: mcp__eco-gis-amap__spatial_overlay
    level: L1
  - tool: mcp__eco-gis-amap__spatial_points_in_polygon
    level: L1
  - tool: mcp__eco-gis-amap__spatial_cluster
    level: L1
  - tool: mcp__eco-gis-amap__spatial_interpolate
    level: L1
  - tool: mcp__eco-gis-amap__spatial_heatmap
    level: L1
  - tool: mcp__eco-gis-amap__spatial_measure
    level: L1
  - tool: mcp__eco-gis-amap__spatial_nearest
    level: L1
  - tool: mcp__eco-gis-amap__eco_site_scan
    level: L1
  - tool: mcp__eco-gis-amap__eco_compliance_check
    level: L1
  - tool: mcp__eco-gis-amap__eco_grid_search
    level: L1
  - tool: mcp__eco-gis-amap__eco_plume_dispersion
    level: L1
  - tool: mcp__eco-gis-amap__eco_trajectory_analyze
    level: L1
  - tool: mcp__eco-gis-amap__eco_spatial_join
    level: L1
  - tool: mcp__eco-gis-amap__eco_source_apportionment
    level: L1
  - tool: mcp__eco-gis-amap__eco_back_trajectory
    level: L1
  - tool: mcp__eco-gis-amap__eco_wind_rose
    level: L1
  - tool: mcp__eco-gis-amap__eco_timeseries_align
    level: L1
  - tool: mcp__eco-gis-amap__eco_anomaly_detect
    level: L1
  - tool: mcp__eco-gis-amap__eco_compliance_stats
    level: L1
  - tool: mcp__eco-gis-amap__eco_emergency_list
    level: L1
  - tool: mcp__eco-gis-amap__eco_static_map
    level: L1
  - tool: mcp__eco-gis-amap__eco_interactive_map
    level: L1
  - tool: mcp__eco-gis-amap__eco_water_map
    level: L1
  - tool: mcp__eco-gis-amap__qgis_run_algorithm
    level: L1
  - tool: mcp__eco-gis-amap__qgis_buffer
    level: L1
  - tool: mcp__eco-gis-amap__qgis_overlay
    level: L1
  - tool: mcp__eco-gis-amap__qgis_reproject
    level: L1
  - tool: mcp__eco-gis-amap__qgis_convert
    level: L1
  - tool: mcp__eco-gis-amap__qgis_slope
    level: L1
  - tool: mcp__eco-gis-amap__qgis_idw_interpolate
    level: L1
  - tool: mcp__zfyth__zfyth_status
    level: L1
  - tool: mcp__zfyth__zfyth_query
    level: L1
  - tool: mcp__zfyth__zfyth_menu
    level: L1
  - tool: mcp__zfyth__zfyth_view_config
    level: L1
  - tool: mcp__zfyth__zfyth_query_by_name
    level: L1
  - tool: mcp__zfyth__zfyth_list_modules
    level: L1
  - tool: mcp__zfyth__zfyth_pollution_source
    level: L1
  - tool: mcp__zfyth__zfyth_form_get
    level: L1
  - tool: mcp__cepc__veto_rules_list
    level: L1
  - tool: mcp__cepc__public_project_search
    level: L1
  - tool: mcp__cepc__project_list
    level: L1
  - tool: mcp__cepc__project_detail
    level: L1
  - tool: mcp__cepc__region_statistics
    level: L1
  - tool: mcp__cepc__user_info
    level: L1
  - tool: mcp__cepc__user_menus
    level: L1
  - tool: mcp__cepc__notifications
    level: L1
  - tool: mcp__cepc__check_tasks
    level: L1
  - tool: mcp__cepc__export_tasks
    level: L1
  - tool: mcp__cepc__problem_projects
    level: L1
  - tool: mcp__cepc__area_tree
    level: L1
  - tool: mcp__cepc__dict_map
    level: L1
  - tool: mcp__sthjzf__list_views
    level: L1
  - tool: mcp__sthjzf__query_view
    level: L1
  - tool: mcp__sthjzf__get_menu
    level: L1
  - tool: mcp__sthjzf__get_view_config
    level: L1
  - tool: mcp__sthjzf__query_cases
    level: L1
  - tool: mcp__sthjzf__list_depts
    level: L1
  - tool: mcp__sthjzf__query_case_detail
    level: L1
  - tool: mcp__sthjzf__query_case_statistics
    level: L1
  - tool: mcp__sthjzf__water_current_user
    level: L1
  - tool: mcp__sthjzf__water_task_statistics
    level: L1
  - tool: mcp__sthjzf__water_task_list
    level: L1
  - tool: mcp__sthjzf__water_supervise_statistics
    level: L1
  - tool: mcp__sthjzf__status
    level: L1
  - tool: mcp__wryzxjc__status
    level: L1
  - tool: mcp__wryzxjc__list_regions
    level: L1
  - tool: mcp__wryzxjc__list_pollution_sources
    level: L1
  - tool: mcp__wryzxjc__get_pollution_source
    level: L1
  - tool: mcp__wryzxjc__list_alarms
    level: L1
  - tool: mcp__wryzxjc__list_devices
    level: L1
  - tool: mcp__wryzxjc__list_realtime_data
    level: L1
  - tool: mcp__wryzxjc__list_jcd_tree
    level: L1
  - tool: mcp__wryzxjc__list_history_data
    level: L1
  - tool: mcp__permit_enterprise__auth_status
    level: L1
  - tool: mcp__permit_enterprise__company_profile
    level: L1
  - tool: mcp__permit_enterprise__company_menu
    level: L1
  - tool: mcp__permit_enterprise__license_apply_list
    level: L1
  - tool: mcp__permit_enterprise__license_reapply_list
    level: L1
  - tool: mcp__permit_enterprise__license_change_list
    level: L1
  - tool: mcp__permit_enterprise__license_adjust_list
    level: L1
  - tool: mcp__permit_enterprise__license_renew_list
    level: L1
  - tool: mcp__permit_enterprise__license_reissue_list
    level: L1
  - tool: mcp__permit_enterprise__soil_manage_list
    level: L1
  - tool: mcp__permit_enterprise__register_list
    level: L1
  - tool: mcp__permit_enterprise__disclosure_list
    level: L1
  - tool: mcp__permit_enterprise__license_apply_check
    level: L1
  - tool: mcp__permit_enterprise__self_acceptance
    level: L1
  - tool: mcp__permit_enterprise__report_list
    level: L1
  - tool: mcp__permit_enterprise__unified_report_list
    level: L1
  - tool: mcp__permit_enterprise__monitor_info
    level: L1
  - tool: mcp__permit_enterprise__monitor_month_status
    level: L1
  - tool: mcp__permit_enterprise__ledger_list
    level: L1
  - tool: mcp__permit_enterprise__auto_monitor
    level: L1
  - tool: mcp__permit_enterprise__eia_apply
    level: L1
  - tool: mcp__permit_enterprise__carbon_report
    level: L1
  - tool: mcp__permit_enterprise__correction_status
    level: L1
  - tool: mcp__epxz__xz_user_info
    level: L1
  - tool: mcp__epxz__xz_search_reports
    level: L1
  - tool: mcp__epxz__xz_search_terms
    level: L1
  - tool: mcp__epxz__xz_search_files
    level: L1
  - tool: mcp__epxz__xz_search_shares
    level: L1
  - tool: mcp__epxz__xz_publicity_list
    level: L1
  - tool: mcp__epxz__xz_publicity_detail
    level: L1
  - tool: mcp__epxz__xz_communication
    level: L1
  - tool: mcp__permit_management__permit_status
    level: L1
  - tool: mcp__permit_management__permit_menu
    level: L1
  - tool: mcp__permit_management__permit_license_list
    level: L1
  - tool: mcp__permit_management__permit_enterprise_list
    level: L1
  - tool: mcp__permit_management__permit_jgzf_menu
    level: L1
  - tool: mcp__permit_management__permit_jgzf_license_execution
    level: L1
  - tool: mcp__permit_management__permit_jgzf_stop_production
    level: L1
  - tool: mcp__permit_management__permit_jgzf_enterprise_archive
    level: L1
  - tool: mcp__permit_management__permit_area_list
    level: L1
  - tool: mcp__permit_management__permit_industry_list
    level: L1
  - tool: mcp__zfyth__zfyth_login
    level: L4
  - tool: mcp__zfyth__zfyth_case_finish
    level: L4
  - tool: mcp__zfyth__zfyth_case_delete
    level: L4
  - tool: mcp__zfyth__zfyth_case_assign
    level: L4
  - tool: mcp__zfyth__zfyth_form_save
    level: L4
  - tool: mcp__zfyth__zfyth_case_save_step
    level: L4
  - tool: mcp__zfyth__zfyth_case_start
    level: L4
  - tool: mcp__zfyth__zfyth_case_upload
    level: L4
  - tool: mcp__zfyth__zfyth_case_upload_delete
    level: L4
  - tool: mcp__zfyth__zfyth_case_upload_callback
    level: L4
  - tool: mcp__zfyth__zfyth_task_create
    level: L4
  - tool: mcp__cepc__cepc_login
    level: L4
  - tool: mcp__cepc__project_audit
    level: L4
  - tool: mcp__cepc__batch_audit
    level: L4
  - tool: mcp__cepc__report_export
    level: L4
  - tool: mcp__cepc__export_create
    level: L4
  - tool: mcp__cepc__system_config
    level: L4
  - tool: mcp__sthjzf__login
    level: L4
  - tool: mcp__sthjzf__water_clue_verify
    level: L4
  - tool: mcp__sthjzf__water_clue_confirm
    level: L4
  - tool: mcp__sthjzf__water_api
    level: L4
  - tool: mcp__wryzxjc__login
    level: L4
  - tool: mcp__wryzxjc__raw_query
    level: L4
  - tool: mcp__permit_enterprise__auth_login
    level: L4
  - tool: mcp__permit_enterprise__auth_logout
    level: L4
  - tool: mcp__epxz__xz_login
    level: L4
  - tool: mcp__epxz__xz_download
    level: L4
  - tool: mcp__epxz__xz_raw_call
    level: L4
  - tool: mcp__permit_management__permit_login
    level: L4
```