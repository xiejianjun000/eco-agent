---
name: eco-enforcement-platform
description: 湖南生态环境智慧执法办案系统 标准化对接 Skill。覆盖 CONNECT→SCAN→SYNC→INSPECT→ACT 完整 SOP 流程，支持案卷台账/文书管理/一源一档数据提取与巡检报告生成.
version: 1.0.0
author: EcoAegis Team
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [enforcement, case-management, government-platform, data-extraction]
    category: enforcement
    related_skills: [ecoaegis-auth]
    config:
      toolsets: [ecoaegis]
      requires: [requests, playwright]
      optional: [pycryptodome, ddddocr]
---

# 执法办案 Skill — 标准化平台对接

本 Skill 是 EcoAegis 执法办案模块的核心驱动，实现与「湖南生态环境智慧执法办案系统」的全栈对接。设计遵循 **SOP 六阶段标准化流程**，适配所有 Boanda queryservice 框架的政务平台。

## When to Use

- **首次接入**：新平台注册后执行 CONNECT → SCAN → SYNC
- **日常巡检**：每日自动执行 INSPECT，生成巡检报告
- **数据更新**：案件状态变更后触发增量同步
- **案卷归档**：结案案件自动进入评查 → 归档流程
- **文书下载**：批量下载平台文书文件供 AI 学习
- **企业画像**：拉取一源一档企业数据进行风险分析

## Architecture

```
 ┌──────────────────────────────────────────────────────────────┐
 │                     SOP 六阶段流程                             │
 │                                                               │
 │  DISCOVER ──▶ CONNECT ──▶ SCAN ──▶ SYNC ──▶ INSPECT ──▶ ACT │
 │  平台发现      建立连接    模块扫描   数据同步   日常巡检   触发动作 │
 └──────────────────────────────────────────────────────────────┘

 实现文件：eco-bridge/skills/enforcement_platform.py
 API 网关：eco-bridge/server.py  (/api/enforcement/*)
 前端客户端：app/src/lib/hermesClient.ts
```

## How to Run

### 方式 1：通过 eco-bridge API

```bash
# 1. 连接平台（复用 Chrome 已有登录会话）
curl -X POST http://localhost:8787/api/enforcement/connect \
  -H "Content-Type: application/json" \
  -d '{"mode": "chrome", "chromePort": 9222}'

# → {"ok": true, "sessionToken": "abc123..."}

# 2. 扫描平台模块
curl -X POST http://localhost:8787/api/enforcement/scan \
  -H "Content-Type: application/json" \
  -d '{"sessionToken": "abc123..."}'

# 3. 全量同步
curl -X POST http://localhost:8787/api/enforcement/sync \
  -H "Content-Type: application/json" \
  -d '{"sessionToken": "abc123...", "outputDir": "/tmp/data"}'

# 4. 日常巡检
curl -X POST http://localhost:8787/api/enforcement/inspect \
  -H "Content-Type: application/json" \
  -d '{"sessionToken": "abc123..."}'
```

### 方式 2：直接调用 Python 模块

```python
from skills.enforcement_platform import EnforcementPlatform

p = EnforcementPlatform()
p.connect_via_chrome()                    # 复用 Chrome 会话
cases = p.get_cases(page=1, rows=100)     # 获取案卷列表
docs = p.get_documents(page=1, rows=100)  # 获取文书列表
report = p.inspect()                      # 日常巡检
```

## Endpoint Reference

### POST /api/enforcement/connect

连接平台，三种模式：

| mode 参数 | 说明 | 需要的额外参数 |
|-----------|------|---------------|
| `chrome` | 复用 Chrome 已有会话 | `chromePort` (默认 9222) |
| `session` | 使用已知 JSESSIONID | `jsessionid` |
| `login` | 完整登录流程 | `username`, `password` |

### POST /api/enforcement/scan

扫描平台模块，返回标准化 Manifest：
- 自动识别 queryservice 框架的 viewId
- 自动映射字段到 EcoAegis 标准 Schema
- 生成模块清单（案卷台账/文书管理/一源一档）

### POST /api/enforcement/sync

全量同步：
- 案卷数据 → `/tmp/eco-aegis-sync/cases.json`
- 文书列表 → `/tmp/eco-aegis-sync/documents.json`
- 文书文件 → `/tmp/eco-aegis-sync/document_files/`
- 企业数据 → `/tmp/eco-aegis-sync/enterprises.json`

### POST /api/enforcement/inspect

每日巡检，返回 InspectionReport：
- 新增案件统计
- 状态变更统计
- 审核驳回告警
- 结案率计算

### GET /api/enforcement/cases?token=&page=&rows=

分页获取标准化案卷列表，字段已映射为 EcoAegis 格式。

### GET /api/enforcement/documents?token=&page=&rows=

获取文书管理列表（74 份文书）。

### GET /api/enforcement/document-download?token=&fileId=

下载单份文书文件到本地。

### POST /api/enforcement/export

导出模块数据为 Excel 文件。

## Standardized SOP Pipelines

### Pipeline 1: 首次接入

```
connect(chrome) → scan() → sync(full)
```

### Pipeline 2: 日常巡检

```
connect(session) → inspect()
  ├── 对比上次同步数据
  ├── 生成巡检报告
  └── 告警推送（审核驳回/超期未结）
```

### Pipeline 3: 全量数据学习

```
connect(chrome) → sync(full) → download_all_documents()
  ├── 案卷结构化数据 → 学习案件类型分布/处罚金额范围
  ├── 文书文件 → 学习文书模板和内容结构
  └── 企业档案 → 学习污染源分类/监管级别
```

### Pipeline 4: 结案→评查→归档（触发式）

```
案件 stage 变为 enforcement
  → inspect() 检测到状态变更
  → 触发案卷评查 review
  → 文书齐全 → 自动归档 archive
```

## Platform Adaptability

本 Skill 的核心抽象层 **PlatformManifest** 使其可以适配任何 Boanda queryservice 框架的政务平台：

| 适配要点 | 实现方式 |
|---------|---------|
| 不同平台 URL | `BASE_URL` 构造函数参数 |
| 不同模块 viewId | `VIEW_IDS` 字典配置 |
| 不同字段映射 | `CASE_FIELD_MAP` 字典配置 |
| 不同枚举值 | `STAGE_MAP` / `AUDIT_STATUS_MAP` 字典配置 |
| Vue SPA 模块 | 独立抓取逻辑分支 |

**换平台只需改常量配置，代码逻辑零修改。**

## Prerequisites

### 必需
- Python 3.9+
- `requests` — HTTP 调用
- `playwright` — 浏览器自动化（复用 Chrome 会话时）

### 可选
- `pycryptodome` (`pip install pycryptodome`) — AES 密码加密（完整登录时）
- `ddddocr` (`pip install ddddocr`) — 验证码 OCR（完整登录时）

### Chrome 配置（复用会话时）
启动 Chrome 时添加：
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222
```

## Pitfalls

- **JSESSIONID 会在 Chrome 关闭时丢失**：如果 eco-bridge 重启需要重新 connect
- **queryservice API 需要正确的 Content-Type**：POST 时必须是 `application/json`
- **验证码 OCR 准确率约 40%**：复杂算术验证码建议用 Chrome 会话复用方式
- **一源一档是独立 Vue SPA**：数据抓取需要直接调用其内部 API，当前版本仅返回页面 HTML
- **不要频繁全量同步**：每次 sync 会拉取全部数据，建议每日最多执行一次

## Verification

```bash
# 1. 验证 Python 模块加载
cd eco-bridge && python3 -c "from skills.enforcement_platform import EnforcementPlatform; print('OK')"

# 2. 验证 eco-bridge API 端点注册
# 启动 server.py 后查看启动日志中的 "执法办案 Skill" 区块

# 3. 验证 Chrome 连接（需 Chrome 已登录平台 + 调试端口）
curl -X POST http://localhost:8787/api/enforcement/connect \
  -H "Content-Type: application/json" \
  -d '{"mode":"chrome"}'

# 4. 验证数据提取
curl -X POST http://localhost:8787/api/enforcement/scan \
  -H "Content-Type: application/json" \
  -d '{"sessionToken":"<from connect>"}'
```
