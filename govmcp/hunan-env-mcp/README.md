# hunan-env-mcp

湖南省生态环境厅公开数据查询 MCP Server。基于 2026-08-27 对官网（https://sthjt.hunan.gov.cn）的穿透式调研开发，提供空气质量实时数据与政务栏目检索能力，可接入 Claude Desktop / Cursor / 自研 Agent 等任意 MCP 客户端。

## 能力一览

| 类别 | 工具 | 说明 |
|---|---|---|
| 空气质量 | `air_quality_realtime` | 14 市州 + 全省实时 AQI（分钟级） |
| 空气质量 | `air_quality_hourly` | 城市逐小时 AQI 序列 |
| 空气质量 | `air_quality_forecast` | 最新空气质量预报/预警 |
| 空气质量 | `air_quality_rank_daily` | 按日城市空气质量排名 |
| 政务栏目 | `eia_publicity_search` | 环评公示（受理/拟审批/决定） |
| 政务栏目 | `policy_document_search` | 规范性文件/政策解读 |
| 政务栏目 | `notice_announcement_list` | 通知公告 |
| 政务栏目 | `environmental_quality_monthly` | 环境质量月报 |
| 政务栏目 | `env_statistics_report` | 环境统计年报 |
| 政务栏目 | `enforcement_case_search` | 执法案例/处罚公开 |
| 政务栏目 | `credit_evaluation_query` | 企业环保信用评价 |
| 政务栏目 | `news_dynamic_list` | 新闻动态（环保动态/环境要闻/市州新闻/时政关注/图片新闻） |
| 政务栏目 | `interaction_list` | 互动交流（调查征集主题/结果反馈/在线访谈） |
| 政务栏目 | `key_domain_list` | 重点领域（核与辐射/环境影响评价/应急管理/生态保护/土壤污染防治） |
| 政务栏目 | `legal_document_list` | 法规类公开文件（地方性法规/以案说法·以案释法） |
| 政务栏目 | `management_public_list` | 管理与监督公开（执法事前事中/专项资金/规划计划/政协提案答复/信息公开年报/投诉举报） |
| 政务栏目 | `org_structure_list` | 机构信息（领导分工/内设机构/直属单位/人事任免） |
| 政务栏目 | `media_center_list` | 媒体互动（环保视频/新闻发布会/新媒体问政） |
| 政务栏目 | `document_detail` | 详情页全文+附件解析 |
| 检索 | `site_search` | 站群全文检索（省级统一搜索） |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt   # 或 pip install mcp curl_cffi beautifulsoup4 cachetools tenacity pydantic

# 2.（可选）配置空气 API 凭据，见 .env.example
export HUNAN_AIR_API_PASSWORD=xxxx

# 3. 运行（stdio 模式）
python -m hunan_env_mcp.server
# 或 HTTP 模式
python -m hunan_env_mcp.server http
```

## 接入 MCP 客户端

Claude Desktop `claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "hunan-env": {
      "command": "/app/runtime/binaries/python/current/bin/python3",
      "args": ["-m", "hunan_env_mcp.server"],
      "env": { "HUNAN_AIR_API_PASSWORD": "xxxx" }
    }
  }
}
```

## 工程结构

```
src/hunan_env_mcp/
├── server.py            # FastMCP 入口
├── config.py            # 站点常量/栏目表/限速缓存配置
├── datasource/
│   ├── http_client.py   # curl_cffi 指纹模拟 + 限速 + 缓存 + 重试
│   ├── air_api.py       # 实时空气 API（token 自动续期）
│   └── web_crawler.py   # 政务栏目通用爬虫
└── tools/
    ├── air.py           # 空气质量工具
    ├── gov.py           # 政务栏目工具
    └── search.py        # 站内检索工具
```

## 关键设计

- **反爬**：主站为 TLS/HTTP2 指纹级 WAF，统一使用 curl_cffi `impersonate="chrome"` 模拟 Chrome 指纹，curl/requests 直连不可用。
- **限速**：全局限速 1 req/s（令牌桶），列表翻页自带间隔。
- **缓存**：静态 HTML 缓存 10 分钟，实时 API 缓存 60 秒，避免重复请求。
- **凭据安全**：空气 API 账号密码不内置，从环境变量注入；未配置时工具返回明确提示。
- **合规**：仅封装主动公开信息，低频率采集；办件/依申请公开/互动交流（需省级统一身份认证）不在范围内。

## 已知边界

- 实时空气 API 为第三方服务商（雷特软件），非标准端口 9020/8031，接口字段/地址可能变动，需关注官网 iframe 变化。
- 水环境实时专网（218.77.58.37:8443）公网不可达，未接入。
- 环境质量月报/统计年报为页面文章，返回正文需调用 `document_detail` 展开。

## 实测验证记录（2026-08-27）

- 单元冒烟测试 5 项全部 PASS（tests/test_smoke.py，不依赖外网）
- P2/P3 扩展验证：单元测试 7/7 PASS（tests/test_p23_unit.py），stdio 协议级验证 10/10 PASS（20 工具注册全链路调用）
- 真实数据抓取验证：
  - notice_announcement_list：通过统一检索接口返回 40 条（公告 97434 + 通知 97433）
  - eia_publicity_search：静态 HTML 解析返回 20 条，详情页可提取 3 个 PDF 附件
  - policy_document_search：list_sy3 模板解析返回 20 条
  - org_structure_list：领导分工返回 5 条，内设机构按关键词过滤（如"督察"）正常
  - media_center_list：环保视频返回列表，详情页全文联动解析正常
- 站点访问特性：主站 TLS 指纹级 WAF（curl/requests 直连被断），本项目统一走 curl_cffi impersonate=chrome；
  API 域名 api.hunan.gov.cn 与 hn.leitesoft.cn:9020 可直连。
