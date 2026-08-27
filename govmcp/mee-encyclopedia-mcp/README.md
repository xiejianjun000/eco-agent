---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: c3e1d189ed77864364abef970f361174_e48508c6a1db11f193c6525400f8a581
    ReservedCode1: oXLOLy6jTekgHSLC7+5filsCz0ZX47mTWrZg6TQaoIja9y++mdCjboK+m5rdUFWqMz//C+VElVBcb8Zoqhutv7fs7xxu/u3/DAKvKvZx6KJtUVzf03PgWdOcyEUWuKI3MMuh4Rz9JqulihiyOpvrMMPd0xx84pmsq3tJQHtUxQ2fTyEPANnX6VHev0g=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: c3e1d189ed77864364abef970f361174_e48508c6a1db11f193c6525400f8a581
    ReservedCode2: oXLOLy6jTekgHSLC7+5filsCz0ZX47mTWrZg6TQaoIja9y++mdCjboK+m5rdUFWqMz//C+VElVBcb8Zoqhutv7fs7xxu/u3/DAKvKvZx6KJtUVzf03PgWdOcyEUWuKI3MMuh4Rz9JqulihiyOpvrMMPd0xx84pmsq3tJQHtUxQ2fTyEPANnX6VHev0g=
---

# MEE Encyclopedia MCP（生态环境百科全书 MCP Server）

将生态环境部官网（mee.gov.cn）及下属单位网站矩阵（20+ 直属单位、19 派出机构、20+ 业务系统）封装为**一个统一入口的 MCP Server**，让 AI 实时获取生态环境垂直领域权威信息，支持**读取（read）与下载（download）**两类硬能力。

## 特性

- 单入口：对外仅暴露 `mee-encyclopedia-mcp` 一个 MCP Server
- 15 大领域命名空间：air / water / soil / solidwaste / noise / radiation / ecology / eia / regulation / climate / intl / sciedu / news / quality / interact
- **46 个工具**：覆盖主站 60+ 栏目（要闻/政策文种/业务工作 21 栏目/环境质量报告/互动交流/曝光台/党建/专题/核安全局子站/英文版/站内搜索）
- 读取能力：网页正文、实时环境质量、预报、排污许可、环评信用、标准、政策、环境质量公报/月报等
- 下载能力：标准 PDF、附件、数据导出（CSV/JSON）、任意公开 URL 文件
- 数据分层：页面解析 + 缓存 / Web 查询封装 / RAG 知识库 / 授权接口（预留）
- 合规内建：只读优先、来源 URL 绑定、限流、审计日志、PII 最小化

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
python -m mee_encyclopedia.server
```

## 目录结构

```
src/mee_encyclopedia/
├── server.py          # MCP Server 主入口（统一对外）
├── registry.py        # 领域模块注册
├── core/              # 核心基础设施
│   ├── fetcher.py     # HTTP 抓取（超时/重试/UA）
│   ├── parser.py      # HTML/PDF 解析
│   ├── cache.py       # 内存+磁盘二级缓存
│   ├── reader.py      # 读取工具族
│   └── downloader.py  # 下载工具族
├── domains/           # 13 领域模块
└── rag/               # RAG 知识库（政策/标准问答）
```

## 工具示例

| 命名空间 | 工具 | 说明 |
|---|---|---|
| read | read_web_page | 读取任意公开网页正文 |
| read | read_air_quality | 城市实时空气质量 |
| read | read_air_forecast | 空气质量预报 |
| read | read_surface_water | 地表水水质 |
| read | read_sea_water | 海水水质 |
| read | read_radiation_level | 辐射剂量率 |
| read | read_mee_list | 主站 60+ 栏目列表（要闻/政策/业务/质量/互动/曝光台/核安全局等） |
| read | list_mee_categories | 全部栏目分组导览 |
| read | read_mee_article | 主站文章正文 |
| read | read_policy_type / read_policy_interpretation | 按文种读政策 / 政策解读 |
| read | read_quality_report | 环境质量公报/年报/月报 |
| read | read_interact / read_exposure | 互动交流 / 曝光台 |
| read | read_nnsa_list | 国家核安全局子站 |
| read | read_english_list | 英文版栏目 |
| read | search_site | 官网站内搜索 |
| read | search_standard / read_standard | 标准检索/详情 |
| read | search_policy / read_policy | 政策检索/全文 |
| read | search_permit | 排污许可查询 |
| read | query_eia_credit | 环评信用查询 |
| read | search_policy | 政策检索 |
| download | download_file | 下载公开 URL 文件到本地 |
| download | download_standard_pdf | 下载标准 PDF |
| download | export_air_quality_csv | 导出空气质量数据 CSV |
| download | export_mee_list | 导出栏目列表 CSV/JSON |
*（内容由AI生成，仅供参考）*


## 生产部署（v1.0.0）

### 快速安装

```bash
bash deploy/install.sh            # 创建 venv、安装依赖、冒烟测试
bash deploy/install.sh --with-service   # 额外注册 systemd 服务
bash deploy/healthcheck.sh       # 健康检查（进程/工具数/网络连通）
```

### systemd

`deploy/mee-encyclopedia-mcp.service`：stdio 传输守护，含 `NoNewPrivileges`、`ProtectSystem`、`PrivateTmp` 等最小权限加固；工作目录仅开放 `work/` 可写。

### 启动方式

```bash
# stdio（默认，供 Claude Desktop / IDE 等 MCP 客户端托管）
.venv/bin/mee-encyclopedia-mcp --transport stdio

# SSE / streamable-http（远程网关场景）
.venv/bin/mee-encyclopedia-mcp --transport sse
.venv/bin/mee-encyclopedia-mcp --transport streamable-http
```

### 合规红线（只读约束）

- 仅读取公开页面与公开接口，不登录、不提交表单、不交互式操作；
- 限速 2~4s 随机间隔 + 指数退避 + 缓存优先，避免触发反爬；
- 依申请公开 / 办事大厅 / 写信投诉等需登录交互的能力**不实现**。
