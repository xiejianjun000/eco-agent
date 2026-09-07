# MCP 接入记录：ehs-kb-ops（EHS 知识库操作服务）

日期：2026-07-20
执行者：生态环境执法督察评查专家（OpenClaw agent）

## 目标
用户要求接入其自建 MCP 服务 `ehs-kb-ops`，使其在本地可用。

## 服务信息
- SSE 端点：`http://111.230.89.107:8000/sse/`
- 鉴权：`X-API-Key` 请求头（用户提供的 key）
- 实现：MCP-over-SSE（旧版传输），serverInfo = `ehs-kb-ops-remote v1.28.1`
- 底层：git 托管的 EHS wiki（flowwiki，路径 `/var/www/ehs-wiki/flowwiki/`）

## 接入过程与发现

### 1. mcporter 配置（成功）
`mcporter config add ehs-kb-ops "http://111.230.89.107:8000/sse/" --transport sse --header "X-API-Key=..." --scope home`
- 配置写入 `/Users/mac/.mcporter/mcporter.json`
- 但 `mcporter list/call` 均挂起（POST 拿 202 后等不到 SSE 响应，30s+ 超时）

### 2. 手动端到端验证（SSE 协议本身 OK）
用 curl 实测完整握手：
- GET /sse/ → 收到 `event: endpoint`，`data: /sse/messages/?session_id=xxx`（注意是**相对路径**）
- POST initialize → `202 Accepted`
- SSE 流回传 `event: message`，带完整 `result`
→ 证明**服务器协议实现正确**，响应确实推回初始 SSE 连接。

### 3. DeepSeek 的问题（用户已查明，与服务端无关）
- DeepSeek 的 MCP 客户端把 endpoint 拼成了 `/sse/sse/messages/`（多一层 /sse/），导致 404
- 用户已在服务端兼容双 `/sse/` 路径，DeepSeek 复测可用

### 4. 根因区分（重要）
- DeepSeek 失败 = URL 拼接 bug（客户端），已服务端兼容修复
- 本机 mcporter 挂起 = 另一类客户端问题：拿到 202 后读不到 SSE 响应事件（疑似 mcporter 的 SSE 会话/读连接管理与该服务端单连接响应推送不匹配）
- 两者**不是同一个 bug**

### 5. 自建可用客户端（已落地）
鉴于 mcporter 挂起、但协议本身可用，写了一个单连接模式的 MCP-over-SSE 客户端封装：
- 路径：`/Users/mac/.qclaw/workspace-agent-6458195c/mcp_sse_client.py`
- 关键修复：用 `urllib.parse.urljoin` 把 endpoint 的**相对路径**解析为绝对 URL（否则 urllib 报 `unknown url type`）
- 用法：
  - `python3 mcp_sse_client.py <sse_url> <api_key> --status`        # kb_status
  - `python3 mcp_sse_client.py <sse_url> <api_key> --list`           # 列出工具
  - `python3 mcp_sse_client.py <sse_url> <api_key> <tool> '<json>'`  # 调任意工具

## 验证结果（全部 ✅）
- TCP 8000 可达 ✅
- SSE endpoint 事件正常 ✅
- kb_status：返回分支/提交/磁盘状态 ✅
- kb_search "危废台账"：命中 18 条（flowwiki 语料）✅
- kb_list：返回 6 个工具 ✅

## 已发现工具清单（6 个）
| 工具 | 说明 | 鉴权 |
|------|------|------|
| kb_upload | 上传/更新文件（git add→commit→push） | 需 API Key |
| kb_delete | 删除知识库文件 | 需 API Key |
| kb_sync | 全量同步（git push + 部署校验） | 需 API Key |
| kb_list | 列出目录结构 | 免认证 |
| kb_search | 全文搜索 | 免认证 |
| kb_status | 查看部署状态 | 免认证 |

## 待办 / 备注
- [ ] mcporter 挂起未根治（如需用 mcporter 原生调用，需进一步排查其 SSE 会话管理；当前用自建脚本替代）
- [ ] 用户提及未来做 `kb_log_chat` 收集各 AI 调用记录，可一并加入「AI 调用日记」能力
- 注：本次测试 API Key 已写入本机 mcporter.json，属用户自有服务，无外泄风险
