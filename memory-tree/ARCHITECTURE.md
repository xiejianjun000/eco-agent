# ECO AGENT Memory Tree 架构设计

> **评分制记忆树 — SQLite + Obsidian 双向同步**
> 版本：v0.1.0 · 最后更新：2026-07-28

---

## 1. 核心概念

Memory Tree 是 ECO AGENT 的**长期记忆系统**，基于 OPENHUMAN 的 Memory Tree 架构融合 FlowWiki 知识体系。

### 设计原则

| 原则 | 说明 |
|:-----|:------|
| **人类可读** | 所有记忆节点以 Markdown 格式存储，可在 Obsidian 中直接打开编辑 |
| **双向同步** | SQLite（快速检索）↔ Obsidian Markdown（人类阅读）实时同步 |
| **评分驱动** | 每个节点有重要性评分（0-100），决定加载优先级 |
| **血统追溯** | 每个节点记录 parent_id，形成完整的知识血统链 |
| **分层存储** | Hot（常驻）→ Warm（近期）→ Cold（归档）三级缓存 |

### 节点类型

| 类型 | 说明 | 生命周期 | 评分范围 |
|:-----|:------|:---------|:---------|
| `statute` | 法规知识节点 | 永久 | 70-100 |
| `case` | 执法案例节点 | 永久 | 50-100 |
| `benchmark` | 裁量基准节点 | 永久 | 60-100 |
| `procedure` | 执法程序节点 | 永久 | 70-100 |
| `session` | 会话历史节点 | 90 天 | 20-80 |
| `skill` | 执法技能节点 | 永久 | 60-100 |
| `quality` | 质量审计节点 | 永久 | 30-80 |
| `alert` | 监控告警节点 | 30 天 | 40-90 |

---

## 2. 数据流

```
外部输入（法规更新/案例录入/会话结束）
    ↓
标准化 Markdown 块（≤ 3000 tokens）
    ↓
评分计算（重要性 + 时效性 + 关联度）
    ↓
写入 SQLite（主存储） + 写入 Obsidian Markdown（同步）
    ↓
触发索引更新（BM25 + 向量）
    ↓
分层加载策略：
  Hot（当前会话）→ Warm（近期活跃）→ Cold（长期归档）
```

---

## 3. SQLite Schema

### 3.1 节点表

```sql
CREATE TABLE nodes (
    id          TEXT PRIMARY KEY,        -- 唯一 ID: node_xxxxxxxx
    type        TEXT NOT NULL,           -- statute/case/benchmark/procedure/session/skill/quality/alert
    title       TEXT NOT NULL,           -- 节点标题
    content     TEXT NOT NULL,           -- Markdown 内容（≤ 3000 tokens）
    score       REAL DEFAULT 50.0,      -- 重要性评分 0-100
    tags        TEXT DEFAULT '[]',       -- JSON 标签数组
    parent_id   TEXT,                   -- 父节点 ID（血统链）
    source      TEXT,                   -- 来源（flowwiki/manual/session）
    confidence  TEXT DEFAULT 'medium',  -- high/medium/low
    created_at  TEXT NOT NULL,          -- ISO 8601
    updated_at  TEXT NOT NULL,          -- ISO 8601
    accessed_at TEXT,                   -- 最后访问时间
    access_count INTEGER DEFAULT 0,     -- 访问次数
    FOREIGN KEY (parent_id) REFERENCES nodes(id)
);
```

### 3.2 关联表

```sql
CREATE TABLE edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL,           -- 源节点
    target_id   TEXT NOT NULL,           -- 目标节点
    relation    TEXT NOT NULL,           -- references/referenced_by/related/similar
    weight      REAL DEFAULT 1.0,       -- 关联强度 0-1
    created_at  TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES nodes(id),
    FOREIGN KEY (target_id) REFERENCES nodes(id)
);
```

### 3.3 全文搜索表

```sql
CREATE VIRTUAL TABLE nodes_fts USING fts5(
    title, content, tags,
    content='nodes',
    content_rowid='rowid'
);
```

### 3.4 同步日志表

```sql
CREATE TABLE sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     TEXT NOT NULL,
    direction   TEXT NOT NULL,           -- to_obsidian / to_sqlite
    status      TEXT NOT NULL,           -- success / failed
    file_path   TEXT,                   -- Obsidian 文件路径
    error_msg   TEXT,
    synced_at   TEXT NOT NULL
);
```

---

## 4. 分层加载策略

| 层级 | 范围 | 加载方式 | 容量 | 检索延迟 |
|:-----|:------|:---------|:-----|:---------|
| **Hot** | 当前会话 / 高频访问 | 预加载到内存 | ~50 节点 | < 1ms |
| **Warm** | 7 天内活跃节点 | SQLite 实时查询 | ~500 节点 | < 10ms |
| **Cold** | 全部历史节点 | SQLite + FTS5 索引 | 无限制 | < 100ms |

### Hot 节点选择算法

```
score_weight = 0.5
recency_weight = 0.3
frequency_weight = 0.2

hot_score = score * score_weight 
          + recency_factor * recency_weight 
          + access_count / max_access * frequency_weight
```

---

## 5. 混合检索策略

```
用户查询
    ↓
BM25 全文搜索（FTS5）─── 快速召回 Top 50
    ↓
语义向量检索（如可用）── 补充召回 Top 50
    ↓
RRF 融合（Reciprocal Rank Fusion）
    ↓
BGE 重排序（交叉编码器）
    ↓
Top 10 结果输出
```

---

## 6. Obsidian 同步协议

### 双向同步规则

| 方向 | 触发条件 | 行为 |
|:-----|:---------|:-----|
| SQLite → Obsidian | 节点创建/更新 | 写入 `.md` 文件到 Obsidian 目录 |
| Obsidian → SQLite | 检测到文件变更 | 解析 frontmatter + body 更新数据库 |

### Obsidian 文件格式

```markdown
---
id: node_a1b2c3d4
type: case
score: 85
tags: [env/air, enforcement/penalty]
parent: node_previous
source: manual
confidence: high
created: 2026-07-28
updated: 2026-07-28
---

# 节点标题

正文内容 Markdown ...

## 引用来源
```

---

## 7. ECO Memory Tree 目录结构

```
memory-tree/
├── ARCHITECTURE.md        ← 本文件
├── ECO_SCHEMA.sql         ← SQLite Schema 定义
│
├── data/                   ← SQLite 数据库文件（gitignored）
│   └── eco_memory.db
│
├── obsidian_sync/          ← Obsidian 同步目录
│   ├── statutes/           ← 法规知识
│   ├── cases/              ← 执法案例
│   ├── benchmarks/         ← 裁量基准
│   ├── procedures/         ← 执法程序
│   ├── sessions/           ← 会话归档
│   └── quality/            ← 质量审计
│
└── indices/                ← 索引缓存
    └── bm25_index/
```
