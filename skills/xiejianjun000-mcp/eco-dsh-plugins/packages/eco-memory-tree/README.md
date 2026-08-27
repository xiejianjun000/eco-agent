# eco-memory-tree

dsh plugin — 评分制记忆树：BM25 搜索 + 中文降级 + Obsidian 双向同步。

> 移植自 [xiejianjun000/eco-agent](https://github.com/xiejianjun000/eco-agent) 的 `agent_core/memory_tree.py`（MIT License）。

## 作用

- **评分制节点**：每条记忆带 `score`（重要性）、`tags`、`parent_id`（树形结构）。
- **BM25 排序检索**：英文按 token 计算 BM25；含 CJK 字符时降级为子串命中 + 覆盖率加分（对齐原版 FTS5 + LIKE 中文降级思路）。
- **Obsidian 双向同步**：导出为带 frontmatter 的 Markdown 笔记（`id/score/tags/updated_at`），也从 vault 导入用户编辑后的笔记，按 `updated_at` 保留最新。

## v0.2.0 — 向量检索通道

- 新增 `eco_memory_vector_search`：配置 OpenAI 兼容 embedding 端点后启用向量检索（BM25 + 余弦分数融合排序）。
- 未配置 embedding 时自动降级返回 BM25 结果并标记 `vector_enabled=false`，不阻塞使用。
- 配置方式：`embeddingBaseUrl` / `embeddingApiKey` / `embeddingModel`，或运行时 `ctx.ecoMemory.setEmbeddingFn(fn)`。

## v0.3.0 — 遗忘与维护（eco_memory_prune）

- 新增 `eco_memory_prune` 工具：遗忘机制，按低分（`min_score`）或长期未访问（`max_age_days`，基于 `last_access`）清理节点。
- `security` / `denied` 标签节点始终受保护，不被清理；被删节点的子节点自动提升为根节点。
- `dry_run=true` 预览模式：返回候选数量与样本，不实际删除，方便先评估后执行。

## 安装

```bash
npm install @eco-dsh/eco-memory-tree
```

```ts
import * as ecoMemoryTree from '@eco-dsh/eco-memory-tree'

app.plugin(ecoMemoryTree, {
  storeFile: '~/.eco/dsh/memory/memory_tree.json',
  obsidianVault: '/path/to/vault/eco-memory', // 留空则禁用同步
  syncOnStart: false,
})
```

## 注册工具

| 工具 | 说明 |
|------|------|
| `eco_memory_add` | 添加节点（content / score / tags / parent_id） |
| `eco_memory_search` | 按相关性检索（BM25 + 中文降级 + score 加成） |
| `eco_memory_update` | 更新节点 |
| `eco_memory_delete` | 删除节点 |
| `eco_memory_stats` | 统计：节点数、平均分、标签分布 |
| `eco_memory_sync` | Obsidian 同步：`to` / `from` / `both` |

## 配置项

| 字段 | 默认 | 说明 |
|------|------|------|
| `storeFile` | `~/.eco/dsh/memory/memory_tree.json` | 节点账本路径 |
| `obsidianVault` | `''` | Obsidian vault 目录（空 = 禁用同步） |
| `syncOnStart` | `false` | 启动时先导入一次 vault |

## 许可

MIT。原始实现版权归 [xiejianjun000/eco-agent](https://github.com/xiejianjun000/eco-agent) 所有，本包为 dsh 生态移植版。
