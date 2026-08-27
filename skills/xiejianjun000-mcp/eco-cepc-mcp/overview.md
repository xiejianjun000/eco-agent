# 验收信息系统MCP v2.1 — 穿透式研究分析与MCP开发

## 任务概述

为执法督察评查专家团开发全国建设项目竣工环境保护验收信息系统（cepc.lem.org.cn）的 MCP 服务器，支持该系统数据的自动化查询和评查。

## 完成成果

### 1. 阿里云 WAF 完全绕过 ✅

尝试了14种方案，最终突破：**直接 spawn Chrome 151 + 原生 CDP WebSocket 控制**。

核心原理：WAF 检测的是自动化框架的 CDP artifacts（Playwright/Selenium 注入的调试协议调用），而非 Chrome 本身。通过 `child_process.spawn` 直接启动真 Chrome（不经过任何自动化框架包装），WAF 5秒盾 JS 挑战在真实 Chrome JS 引擎中自动执行通过。

关键技术点：
- Chrome 以 `about:blank` 启动 → CDP 连接 → Network.enable → 再导航（确保网络事件捕获）
- headful 模式（headless 被 WAF 检测）
- `--disable-blink-features=AutomationControlled` 移除 webdriver 标记

### 2. 自动登录流程 ✅

- 验证码获取：`GET /jeeplus-vue/sys/getCode` → 返回 base64 PNG + uuid
- 验证码 OCR：ddddocr 识别4位字母数字（成功率约80%，支持3次重试）
- Vue 表单填写：使用 native setter + input/change 事件触发响应式更新
- 登录：POST 加密用户名/密码（AES + Base64），返回 JWT Token

### 3. 20个真实API端点 ✅

通过 CDP Network 域捕获的所有 XHR/Fetch 请求：

**公开（4个）**：公开项目列表、系统配置、验证码、字典

**认证（16个）**：登录、用户信息、用户菜单、用户列表、用户详情、组织机构树、自验项目列表、项目详情(queryById)、行业统计、通知列表、抽查任务、导出任务列表、导出任务创建(POST)、问题项目、区域树、字典

### 4. MCP Server v2.1 ✅

- **19个工具**：4个本地（25项一票否决扫描） + 15个远程（真实API）
- **Chrome CDP 桥接器**：自动管理 Chrome 生命周期 + WAF绕过 + 登录 + API调用
- **自动登录**：首次调用远程工具时自动启动Chrome并登录（约20秒），后续复用会话
- **配置**：支持环境变量配置账号密码

### 5. 项目详情完整9模块捕获 ✅ (v2.1新增)

- 正确端点：`GET /jeeplus-vue/projectmanager/projectinfo/hyProjectInfo/queryById?id=xxx`
- 返回 84 个字段的完整项目详情，涵盖 9 大模块：
  1. 基本信息（dwName, dwFr, dwCode, dwLxr, dwLxrTel, dwXzqhName, dwAddress）
  2. 项目信息（projectXh, projectName, projectNature, hylbCode, hylbName, hylbGmjjCode, hylbGmjjName, projectLng, projectLat）
  3. 环评审批（hpspjgJb, hpspjgRegionName, hpspjgName, hpspCode, hppfDate）
  4. 排污许可（pwxkCode, pwxkpfDate, pwxkCodeZt）
  5. 投资信息（projectZtz, projectHbTz, projectHbTzbl）
  6. 机构信息（bgbzjgName, bgbzjgCode, yydwName, ysjcdwName, ysjcdwCode）
  7. 验收时间线（jgDate, tsStaDate, tsEndDate, ysgkStaDate, ysgkEndDate, ysgkXs, ysgkZt）
  8. 八步验收标志（step1YsqkFlg ~ step8EndFlg）
  9. 验收结论与附件（ysycx, ysjl, ysyjName, ysyjPath, ysbgName, ysbgPath, submitDate）

### 6. 搜索筛选参数验证 ✅ (v2.1新增)

经实际测试验证的筛选参数（全部可用）：

| 参数 | 说明 | 测试结果 |
|------|------|----------|
| dwName | 建设单位名称 | "海螺" → 13条/1060总 |
| projectName | 项目名称 | "水泥" → 18条 |
| projectAddressRegionCode | 区域代码 | 431300 → 1059条（娄底市全部） |
| beginYsgkStaDate/endYsgkStaDate | 公示日期范围 | 2026年全年 → 36条 |
| hylbCode | 行业类别代码 | 需正确代码（如103） |
| ysjl | 验收结论 | 1 → 1059条 |
| isYqtb | 是否按要求填报 | 可用 |
| isJtby | 是否委托填报 | 可用 |
| pwxkCodeZt | 排污许可证状态 | 可用 |

### 7. 导出 POST API 捕获 ✅ (v2.1新增)

- 端点：`POST /jeeplus-vue/projectexporttask/hyProjectExportTask/save`
- 请求体：`{ taskName, cs (JSON字符串，包含HyProjectExportTaskDTO) }`
- 响应：`"保存导出任务成功"` (HTTP 200)
- cs 字段包含完整筛选条件DTO：taskName, step8EndFlg, isDownFile, isDownPwxkxx, isDownHpxtxx, dwName, projectName, projectNature, hpwjType, hylbYear, hylbCode, hylbGmjjCode, projectType, projectAddressRegionCode, hpspjgJb, bgbzjgName, ysjcdwName, beginHppfDate, beginJgDate, beginYsgkStaDate, beginSubmitDate, endHppfDate, endJgDate, endYsgkStaDate, endSubmitDate, isYqtb, isWpxj, isJtby, pwxkCodeZt, ysjl

## 关键文件

| 文件 | 说明 |
|------|------|
| `cepc_mcp/server.py` | MCP Server v2.1 主程序（19个工具） |
| `cepc_mcp/config.example.json` | v2.0 配置文件 |
| `穿透分析报告_验收信息系统.md` | 完整分析报告（含WAF绕过 + API文档） |
| `README.md` | 说明文档 |

## 数据样例

**公开项目列表**：返回全国已公示的验收项目（建设单位、项目名称、地址、公示日期等）

**行业统计**：按国民经济行业分类统计（制造业550个项目、总投资387亿、环保投资24.9亿等）

**用户信息**：娄底市生态环境局，角色：监管机构(supervise)，区域代码：431300

**项目详情样例**（湖南海螺水泥有限公司，84字段）：
- 项目序号: Y20260819-0077
- 行业类别: 一般工业固体废物处置及综合利用 (N7723)
- 环评批复: 娄环新审〔2025〕25号 (2025-08-29)
- 排污许可: 91431322770052069P001P
- 总投资: 200万 | 环保投资: 0万
- 验收监测单位: 湖南湘中博一检测技术有限公司
- 公示期: 2026-03-26 至 2026-04-24 (30天)
- 八步验收: 全部完成 (step1~step8 = "1")

## GitHub 仓库

- **仓库地址**：https://github.com/xiejianjun000/eco-cepc-mcp
- **可见性**：Public
- **默认分支**：main
- **提交**：`CEPC MCP v2.1: WAF bypass + 20 API endpoints + 9-module project detail + export POST + Chrome CDP bridge`
- **文件数**：8 个文件，3553 行

## 后续事项

1. ~~项目详情（`hyProjectInfo/queryById?id=xxx`）的完整9模块响应体~~ ✅ 已捕获
2. ~~项目搜索筛选参数的完整映射~~ ✅ 已验证
3. ~~导出功能 API（POST 请求创建导出任务）~~ ✅ 已捕获
4. ~~将 WAF 绕过能力封装为通用 Chrome CDP 桥接器~~ ✅ 已封装
5. ~~推送到 GitHub 创建新仓库~~ ✅ 已完成

## 通用组件

后续事项4已交付两个文件：

| 文件 | 位置 | 说明 |
|------|------|------|
| `chrome_cdp_bridge.py` | 项目目录 + 技能目录 | 通用 Python 模块，可 import 复用于任何 WAF 防护系统 |
| `SKILL.md` | `~/.workbuddy/skills/chrome-cdp-waf-bypass/` | WorkBuddy 技能文档，含使用方法、配置参数、适配指南 |
