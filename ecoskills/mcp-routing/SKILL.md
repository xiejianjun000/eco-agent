---
name: mcp-routing
description: MCP 工具路由指南——查企业持证/许可证/监测数据/法规/环评/执法案件/信访/空气质量/地图时，先看快速路由表选对 MCP 端与工具前缀。触发词：许可证、排污许可、持证、重点管理、排放口、监测数据、环评、验收、执法案件、双随机、信访、民意、空气质量、AQI、气象、地图、缓冲区。
---

# MCP 使用手册（给 AI 的路由指南）

## 〇、三条铁律

1. **先用公开端，再碰需登录的端**。排污许可类查询，公开端免登录、公网可查、权威性与管理端同级，能查到就不要去撞管理端的内网墙。
2. **工具名前缀就是坐标**：`mcp__eco-pollution-permit__` = 排污许可公开端，`mcp__eco-permit-management__` = 管理端，`mcp__eco-permit-enterprise__` = 企业端。
3. **空结果不等于查无此数据**。若工具返回「平台拦截」「WAF」「出口 IP 被风控」类报错，那是被拦了，不是没有——换出口或改用本机 MCP，切勿据此断言"该企业未持证"。

## 一、快速路由表

| 用户要什么 | 首选 MCP（工具前缀） | 前置条件 |
|---|---|---|
| 企业是否持证/许可证号/有效期/类别 | `mcp__eco-pollution-permit__permit_pub_*`（公开端） | 无 |
| 重点管理 vs 简化管理 | 同上，`permit_pub_search_licenses` 带 `management` | 无 |
| 排放口经纬度（画图用） | `mcp__eco-pollution-permit__permit_pub_discharge_points` | 无 |
| 许可证副本扫描件/执行报告 | `mcp__eco-pollution-permit__permit_pub_license_pages` 等 | 无 |
| 核发审核/监管档案/考核 | `mcp__eco-permit-management__permit_mgt_*` | 政务内网 + 登录 |
| 企业自助申请/变更/台账 | `mcp__eco-permit-enterprise__permit_ent_*` | 企业账号 |
| 环评报告/术语定义/标准 | `mcp__eco-epxz-mcp__xz_*` | 登录 |
| 竣工环保验收公示/审查 | `mcp__eco-cepc__public_project_*` / `project_audit` | 部分需登录 |
| 国家法规/国标 PDF/部委公告 | `mcp__eco-mee-encyclopedia__read_*` | 无 |
| 湖南政策/环评公示/执法案例 | `mcp__eco-hunan-env__policy_*` / `eia_publicity_*` | 无 |
| 执法案件（湖南办案系统） | `mcp__eco-zfyth__zfyth_*` | 登录 |
| 双随机/督查/综合执法四平台 | `mcp__eco-sthjzf__query_*` | 登录 |
| 污染源在线监测（实时/历史/报警） | `mcp__eco-wryzxjc__list_*` | 登录 |
| 湖南省内空气质量 | `mcp__eco-hnkqzl-mcp__hunan_*` | 无 |
| 全国城市空气质量/排名/预警 | `mcp__eco-cnemc-mcp__get_*` | 无 |
| 气象预报/扩散条件 | `mcp__eco-meteo-mcp__get_*` / `assess_dispersion` | 无 |
| 地图可视化/缓冲区/空间分析 | `mcp__eco-gis-amap__*` | 高德 Key |
| 信访举报件（12369） | `mcp__eco-weixinmanager__wm_*` | 登录 |
| 湖南信访/民意 | `mcp__eco-xinfang__*` / `mcp__eco-minyi__*` | 政务专网 |
| 已入库企业合规知识/SOP | `mcp__ehs-kb-ops__kb_search` | 无 |

## 二、逐个详解（要点）

1. **排污许可三端**：查"有没有证/什么类别/在哪儿"→公开端（`eco-pollution-permit`）；查"局里怎么审"→管理端（`eco-permit-management`，内网 10.100.248.253，公网不可达是常态不是配置错）；办"企业自己要报的"→企业端（`eco-permit-enterprise`）。公开端参数：`registerentername` 子串匹配（填地名圈区域）、`management` 只接受 重点管理/简化管理/1/0。返回「平台拦截」= 出口 IP 被风控，换本机版。
2. **核心知识库（eco-mee-encyclopedia）**：国家法规/标准 PDF/部要闻/全国监测数据，免登录。`list_mee_categories` → `read_mee_list` → `read_mee_article`。别用它查湖南地方文件/实时气象/企业持证。
3. **湖南知识库（eco-hunan-env）**：省厅政策/环评公示/执法案例/省实时空气。
4. **环评知识库（eco-epxz-mcp）**：环评报告/术语定义/标准文件，`xz_login` 后 `xz_search_reports/terms/files`。
5. **验收（eco-cepc）**：公示查询免登录，审查类需登录；有 WAF 反爬，被拦换本地环境别重试。
6. **执法一体化（eco-zfyth）**：`zfyth_login`（自动破解算术验证码）→ 查询。⚠️ 含写工具（案件流转/表单保存），写操作前必须用户确认。
7. **综合执法（eco-sthjzf）**：只读。`login` → `get_menu` → `query_view`。
8. **在线监测（eco-wryzxjc）**：`login` → `list_pollution_sources` → `list_realtime_data/history_data`，可带 `qx=431381`（冷水江）。
9. **省空气（eco-hnkqzl-mcp）**：`hunan_list_stations`（按 city 过滤）→ `hunan_realtime` / `hunan_history_range`（一次取全，别逐日循环）。
10. **全国空气（eco-cnemc-mcp）**：`get_city_air_quality` / `get_air_quality_rank` / `get_city_history`。⚠️ 服务器缺图表依赖，出图用 eco-gis-amap。
11. **气象（eco-meteo-mcp）**：预报/历史/空气质量/扩散条件。⚠️ 模式/再分析数据，不能替代国控站实测作执法依据。
12. **信访（eco-weixinmanager/xinfang/minyi）**：读写型，登录后查件；⚠️ 提交/流转前必须用户确认。
13. **企业合规知识库（ehs-kb-ops）**：`kb_search` 语义检索（自然语言提问），`kb_upload` 入库。⚠️ 全库搜索提交**关键词**而非整句，否则退化为扫描 8 万+ 文件。
14. **GIS（eco-gis-amap）**：地图/缓冲区/插值/POI。坐标先用公开端排放口接口拿——POI 只能补坐标，不能判定企业管理类别。

## 三、常见误区

| 误区 | 正解 |
|---|---|
| 查企业信息用 `permit_mgt_enterprise_list` | 那是管理端，需政务内网。查持证用公开端 `permit_pub_search_licenses` |
| 工具返回空 = 没有这家企业 | 先确认是「查无匹配」还是「平台拦截/未登录/网络不可达」，被拦要换出口 |
| 环境变量报错 = 配置没配 | 先验证；可能是网络不可达（内网 MCP 公网连不上） |
| 空气质量随便找一个源 | 省内 eco-hnkqzl-mcp、全国 eco-cnemc-mcp、气象背景 eco-meteo-mcp（模式数据不作执法依据） |

## 四、运维速查

- **本机 stdio**：改源码即生效，无需重启。
- **服务器 SSE**：改代码需 `systemctl restart <服务名>`（见 /opt/mcp-gateway/SERVER_MCP_LIST.md）。
- **403 排查三板斧**：① 本地 mcp.json Key 与 override.conf 一致？② 改过 override.conf 后 daemon-reload + restart？③ URL 尾斜杠（8000 是 /sse/，其余 /sse）。
- **同一套代码两端都部署的**（公开端/管理端/环评/执法一体化/在线监测/综合执法/验收），改一处必须两端同步。
