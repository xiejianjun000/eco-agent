---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: c3e1d189ed77864364abef970f361174_cc96e0c0a1e511f1abe1525400e6dd8f
    ReservedCode1: NJWv7pof6N4zs+DCuplZqym42Cus+bRWvStMbVpSzCwaQatuiHqVSoqLluXUc3DFHznps6pKH2yl0CzMRN0VafbyYMwviAhLbyPc/zOKHRlhIXaJ44xs8iQRgxXni3BMOMnMZpK1aZBQ2voImDv35w31/lwbAwrJrW3uzKLynrUZJDUQbbYK460tPi8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: c3e1d189ed77864364abef970f361174_cc96e0c0a1e511f1abe1525400e6dd8f
    ReservedCode2: NJWv7pof6N4zs+DCuplZqym42Cus+bRWvStMbVpSzCwaQatuiHqVSoqLluXUc3DFHznps6pKH2yl0CzMRN0VafbyYMwviAhLbyPc/zOKHRlhIXaJ44xs8iQRgxXni3BMOMnMZpK1aZBQ2voImDv35w31/lwbAwrJrW3uzKLynrUZJDUQbbYK460tPi8=
---

# 全国排污许可证公开端 MCP Server

基于全国排污许可证管理信息平台公开端（permit.mee.gov.cn）的穿透式 MCP 服务。
输入任意企业名，即可秒级调出**许可证正副本、排放口经纬度、证后管理实时情况、政策法规全文**。

## 特性

| 能力 | 说明 |
| --- | --- |
| 企业检索 | 省/市/单位名/许可证编号/行业 分页查询，覆盖全国 3.8 万+ 页 |
| 许可证详情 | 基本信息、正本版本、副本摘要、经纬度隐藏字段、排放口点位（AES 自动解密） |
| 副本全文 | 逐页 PNG 下载（约 42 页），对接上层 OCR 还原全文（工艺流程/产品/排放标准） |
| 证后管理 | 执行报告（报告期/治理设施运行/达标情况）、监督执法、自行监测入口 |
| 公告 | 限期整改、注销/撤销/遗失声明 |
| 政策法规 | 6 大分类目录 + 全文明文 + 附件下载 |
| 工程化 | WebShield 会话自动维护、1s 限速、指数退避重试、SQLite 缓存 |

## 快速开始

```bash
pip install -r requirements.txt
python server.py
```

MCP 客户端按标准协议连接后即可调用工具。

## 工具清单

| 工具 | 作用 |
| --- | --- |
| `search_licenses` | 查询许可公开信息列表（返回 dataid） |
| `get_license_detail` | 详情：文本信息 + 经纬度 + 排放口点位 |
| `get_license_pages` | 副本图片页清单 |
| `download_license_page` | 下载副本单页 PNG（供 OCR） |
| `get_qrcode_info` | 排放口二维码地址 |
| `get_post_permit_status` | 证后管理：执行报告/监督执法/自行监测 |
| `get_rectification` | 限期整改公示 |
| `get_announcements` | 注销/撤销/遗失公告 |
| `list_policy_docs` | 政策法规分类目录 |
| `get_policy_detail` | 政策法规全文 |
| `get_discharge_points` | 排放口点位解密结果 |
| `get_monitoring_data` | 自行监测平台对接地址 |

## 架构

```
server.py (FastMCP 入口)
  └─ permit_mcp/tools.py      工具定义（12 个）
      ├─ client.py            WebShield 会话 / 限速 / 重试 / 缓存
      ├─ parser.py            HTML→JSON / AES-ECB 解密 / 表格解析
      └─ config.py            接口地址与常量
```

## 穿透实现要点

1. **免登录**：公开端无需账号，仅需 WebShield 会话 token（自动访问首页预热）。
2. **列表接口**：`POST /perxxgkinfo/syssb/xkgg/xkgg!licenseInformation.action`，参数
   `province/city/unitName/licenseNumber/industry/pageIndex/pageSize`。
3. **详情接口**：`GET xkgkAction!xkgk.action?xkgk=getxxgkContent&dataid=<ID>`，
   经纬度以隐藏 input 字段存在；排放口点位为内联 AES-128-ECB 密文，密钥硬编码于页面 JS，自动解密。
4. **副本图片**：`showImage.action?dataid=<ID>` 拿 pkid 与页数 →
   `downFilePng.action?datafileid=<pkid>_<页码>` 逐页下载 PNG。
5. **证后管理**：执行报告走异步 JSON 接口
   `hpsp-company-sewage!getZxbgByYear.action`（参数 reportYear/dataid），返回年度/季度报告及
   `permitrep` 报告文档链接；自行监测对接 `wryjc.mee.gov.cn`。
6. **法规全文**：`lawsStandardList.action?columntype=<分类>` 列目录 →
   `getNewsDetail.action?pkid=<UUID>` 明文正文（`.file-bottom` 容器提取，已去除导航噪音）。
7. **公告表格**：注销/撤销/遗失为纯表格列表（无详情链接），按列头动态映射解析。

## 自测结果（2026-08-27）

| 验证项 | 结果 |
| --- | --- |
| 依赖环境 | fastmcp 2.14.7 + pydantic 2.13.4 无冲突（勿用 3.4.x，其 wheel 为空壳） |
| 12 个 MCP 工具注册 | 全部通过 |
| stdio 协议连通（list_tools / call_tool） | 通过 |
| `search_licenses`（玛格家居） | 命中 10 条，全库 38132 页 |
| `get_license_detail` | 经纬度 112.92680/23.45318，排放口 12 个，AES 解密正常 |
| `get_license_pages` + `download_license_page` | 42 页清单，单页 PNG 102757 字节 |
| `get_post_permit_status` | 拉取 2024/2025 年报 + 自行监测入口 |
| `get_announcements` | 注销公告 10 条/页，全库 16118 页 |
| `get_policy_detail` | 《排污许可管理条例》全文明文 8099 字符，无导航噪音 |

修复记录：`client.py` 死锁（Lock→RLock）、`get_license_pages` 解析、`download_license_page` 缺
`dataid/fileType` 参数、公告表格解析器、法规正文容器提取。

## 合规说明

- 仅访问**公开端**数据，无登录、无验证码绕过。
- 内置 1 秒请求间隔限速与本地缓存，避免对站点造成压力。
- 实时排放数据属自动监控专网（非公开接口），服务提供自行监测平台入口而非越权抓取。

## 已知边界

- 副本为图片，需 OCR 层（可接入 PaddleOCR / 混元视觉模型）转文本。
- 部分企业无执行报告/监督执法记录时，对应表格为空属正常。
- `get_rectification`（限期整改）接口当前返回空数据，参数待进一步调研。
*（内容由AI生成，仅供参考）*
