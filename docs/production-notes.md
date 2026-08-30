# 生产环境部署注意事项

> 面向把 eco Agent 部署到生产/内网环境的运维与安全人员。

## 1. 资源最低配置

| 资源 | 最低 | 建议 |
|------|------|------|
| 内存 | 2 GB | 4 GB（记忆树 1 万节点 + BM25 索引峰值约 500MB） |
| CPU | 2 核 | 4 核（SSE 流 + 12 台远程 MCP 长连接 + 调度器 + 网关子进程并发） |
| 磁盘 | 2 GB | 10 GB（eco_memory.db WAL + artifacts/*.md + 会话日志 + SM3 审计链 jsonl） |

## 2. 并发连接数限制

- **HTTP/SSE 聊天并发**：≤ 20 个活跃流。每个流占用 1 个 asyncio 任务 + 事件队列，超限会挤占事件循环导致所有流延迟。
- **MCP 长连接**：12 台远程 MCP 各 1 条 SSE 常驻连接（不计入聊天并发），每台 30s 超时红线。
- **审批 API**：`/api/v1/approvals/*` **必须只绑 127.0.0.1**。已加 IP 白名单纵深防御（非本机 403），但仍严禁映射公网——answerer 为客户端自报。

## 3. Embedding 降级策略

- `eco_memory_search(hybrid=true)` 依赖 OpenAI 兼容 embedding 端点。
- **未配置 / 超时 / 断连 → 自动降级纯 BM25**，结果 `vector_enabled=false`、`channel='bm25'`，不阻塞主流程。
- 配置了但调用失败时打 `WARN` 日志（`[memory_tree] 向量检索降级为 BM25`），便于告警；未配置则静默降级（正常路径，不误报）。
- embedding 恢复无需重启（每次检索自动重连）。

## 4. 自定义异常与触发条件

| 异常 | 模块 | 触发条件 | 处理建议 |
|------|------|----------|----------|
| `SessionDurabilityError` | `agent_core/checkpoint_policy.py` | 会话日志哈希链中部损坏且自动修复失败（LLM/工具执行前 fail-closed） | 检查磁盘满/进程被硬杀；该会话请求会被拒绝以保数据一致性 |
| `CNEMCError` | `agent_core/cnemc.py` | 国家环境监测总站数据接口异常（凭证/超时/返回结构不符） | 换备用数据源或稍后重试；已做降级返回，不抛给用户 |
| `SSOError` | `agent_core/sso.py` | 政务平台 SSO/OIDC 认证失败（token 无效、端点不可达） | 检查 `.env` 凭证与内网连通性 |

## 5. CI 门禁说明

每次 PR 触发 `.github/workflows/quality-gate.yml`，门禁顺序：

1. **单元测试（门禁 1-5）**：SQL 注入 / 路径遍历 / 审批 IP 白名单 / 检索性能 / 降级可观测，全绿才继续。
2. **文档一致性**：README 入口命令可执行 + 自定义异常覆盖 + 无 key 友好降级。
3. **API 契约**：`openapi.json` 与主分支 diff，破坏性变更需人工审批。
4. **视觉回归**：Playwright 截关键界面，`pixelmatch` 差异 > 1% 告警。

本地跑门禁：`pytest tests/test_security/ tests/test_performance/ tests/test_docs/ -q`
