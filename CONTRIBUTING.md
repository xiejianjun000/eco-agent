# 贡献指南（CONTRIBUTING）

eco Agent 采用"机器可验证通过"的质量门禁——提交前本地跑一遍，CI 再兜底。

## 提交前必须通过的门禁清单

```bash
# 1. 语法 + lint
python -m ruff check .

# 2. 安全/性能/文档门禁（核心，约 20s）
python -m pytest tests/test_security/ tests/test_performance/ tests/test_docs/ -q

# 3. 全量单测
python -m pytest tests/ -q
```

## 门禁覆盖的回归点（改了就要保证不破）

| 门禁 | 防倒退 |
|------|--------|
| SQL 注入 | 记忆树检索的 `type` 过滤器必须参数化（`?`），禁止 f-string 拼接 |
| 路径遍历 | vault 路径必须经 `validate_vault_path`（resolve + 系统目录黑名单） |
| 审批鉴权 | `/approvals/*` 必须经 `_require_local` IP 白名单 |
| 检索性能 | BM25 索引必须走缓存（`_get_bm25`），禁止每次检索重建 |
| 降级可观测 | 向量检索降级必须打 `WARN` 日志 |

## 提交信息规范

`type(scope): 描述`，type ∈ feat/fix/perf/refactor/docs/test/security。

安全相关修复（SQL 注入、路径遍历、鉴权、越权）一律用 `security` 前缀。

## 对齐度基线

CI 每次运行生成《对齐度快照》，任一维度下降 > 5 分阻断合并。详见 `docs/dsh-alignment-*.md`。
