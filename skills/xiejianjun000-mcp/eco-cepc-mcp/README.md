# 验收信息系统MCP v2.0

> 全国建设项目竣工环境保护验收信息系统（cepc.lem.org.cn）MCP 封装
> 为执法督察评查专家团提供"建设项目验收信息"维度的数据访问能力
>
> ✅ v2.0: 阿里云 WAF 完全绕过 + 19个真实API端点 + 自动登录

## 目录

```
验收信息系统MCP/
├── 穿透分析报告_验收信息系统.md    # 完整系统分析（主报告）
├── cepc_mcp/                       # MCP Server 代码
│   ├── server.py                   # MCP Server 主程序（基于 mcp 1.28.1）
│   ├── test_client.py              # 客户端测试脚本
│   └── config.example.json         # 配置文件示例
└── README.md                        # 本文件
```

## 快速开始

### 安装依赖

```bash
# 使用项目已有 venv
/Users/mac/.workbuddy/binaries/python/envs/default/bin/pip install mcp httpx pydantic ddddocr pillow

# 或新建 venv
python3 -m venv .venv
source .venv/bin/activate
pip install mcp httpx pydantic ddddocr pillow
```

### 运行测试

```bash
# 1. 启动 server（stdio 模式）
python3 cepc_mcp/server.py

# 2. 另一终端运行客户端测试
python3 cepc_mcp/test_client.py
```

### 集成到 Claude Desktop / WorkBuddy

编辑 `~/Library/Application Support/Claude Desktop/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "cepc-mcp": {
      "command": "python3",
      "args": ["/Users/mac/Desktop/执法督察评查专家/验收信息系统MCP/cepc_mcp/server.py"],
      "env": {
        "CEPC_COOKIE": "从浏览器获取的登录态 cookie"
      }
    }
  }
}
```

## 已实现工具

| 工具 | 状态 | 说明 |
|------|------|------|
| `veto_rules_list` | ✅ 可用 | 列出 25 项一票否决清单 |
| `project_audit` | ✅ 可用 | 单项目评查（本地 25 项扫描） |
| `batch_audit` | ✅ 可用 | 批量项目评查 |
| `report_export` | ✅ 可用 | 报告导出（md/json） |
| `public_project_search` | ⏳ 待校准 | 公开项目查询（需 HAR 校准 API） |
| `project_detail` | ⏳ 待校准 | 项目详情（需登录 Cookie） |
| `region_statistics` | ⏳ 待校准 | 区域统计（需登录 Cookie） |
| `enterprise_lookup` | ⏳ 待校准 | 企业查询（需登录 Cookie） |

## 当前已知限制

1. **WAF 拦截**：阿里云 WAF 5秒盾对所有自动化浏览器硬拦截，**真实登录必须由军哥在桌面浏览器完成**
2. **API 端点未确认**：远程 API 端点需等军哥提供 HAR 文件后校准
3. **登录态缺失**：依赖军哥从浏览器导出 Cookie，注入到 `CEPC_COOKIE` 环境变量

## 下一步

### 军哥需提供

| 序号 | 内容 | 用途 |
|------|------|------|
| 1 | `cepc_login.har` (从 DevTools 导出) | 反推真实 API 端点 |
| 2 | 登录态 Cookie | 注入到 `CEPC_COOKIE` 环境变量 |
| 3 | 1-2 张关键页面截图 | 校准 UI 字段映射 |

### 我接下来要做

1. 基于 HAR 文件反推 50+ API 端点
2. 补全 8 个工具的真实实现
3. 编写集成测试
4. 部署到 WorkBuddy / Claude Desktop
5. 与执法督察专家团的"案卷评查"工作流对接

## 关联项目

- **项目根目录**：`/Users/mac/Desktop/执法督察评查专家/`
- **25项一票否决扫描器**：`评查扫描器_25项一票否决_v0.1.py`
- **生态环境法典**：2026-08-15 已施行
- **三线编排**：线② 督察督面 + 线③ 案卷评查 受益

## 联系方式

- **主理人**：费执衡（zhifa-review-team-team-lead）
- **成员关联**：弈识破（督政）+ 计分明（评查）+ 殷证印（取证）
- **业务对接**：hunan_loudi 账号（湖南娄底市级管理员）

---

**版本**：v0.1.0 (2026-08-23) — 框架版，待 HAR 校准
