-- ECO AGENT Memory Tree SQLite Schema
-- 版本: v0.1.0

-- ===== 节点表 =====
CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL CHECK(type IN ('statute','case','benchmark','procedure','session','skill','quality','alert')),
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    score       REAL DEFAULT 50.0 CHECK(score >= 0 AND score <= 100),
    tags        TEXT DEFAULT '[]',
    parent_id   TEXT,
    source      TEXT DEFAULT 'manual' CHECK(source IN ('flowwiki','manual','session','import','system')),
    confidence  TEXT DEFAULT 'medium' CHECK(confidence IN ('high','medium','low')),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    accessed_at TEXT,
    access_count INTEGER DEFAULT 0,
    FOREIGN KEY (parent_id) REFERENCES nodes(id)
);

-- ===== 关联表 =====
CREATE TABLE IF NOT EXISTS edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    relation    TEXT NOT NULL CHECK(relation IN ('references','referenced_by','related','similar','derived_from','supersedes')),
    weight      REAL DEFAULT 1.0 CHECK(weight >= 0 AND weight <= 1),
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES nodes(id),
    FOREIGN KEY (target_id) REFERENCES nodes(id)
);

-- ===== 全文搜索索引 =====
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    title,
    content,
    tags,
    content='nodes',
    content_rowid='rowid',
    tokenize='unicode61'
);

-- ===== 同步日志 =====
CREATE TABLE IF NOT EXISTS sync_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     TEXT NOT NULL,
    direction   TEXT NOT NULL CHECK(direction IN ('to_obsidian','to_sqlite')),
    status      TEXT NOT NULL CHECK(status IN ('success','failed','skipped')),
    file_path   TEXT,
    error_msg   TEXT,
    synced_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (node_id) REFERENCES nodes(id)
);

-- ===== 元数据表 =====
CREATE TABLE IF NOT EXISTS metadata (
    key         TEXT PRIMARY KEY,
    value       TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ===== 索引 =====
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_score ON nodes(score DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_updated ON nodes(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);

-- ===== 触发器：自动更新 updated_at =====
CREATE TRIGGER IF NOT EXISTS trg_nodes_updated
    AFTER UPDATE ON nodes
    FOR EACH ROW
BEGIN
    UPDATE nodes SET updated_at = datetime('now') WHERE id = OLD.id;
END;

-- ===== 初始化元数据 =====
INSERT OR IGNORE INTO metadata (key, value) VALUES ('schema_version', '0.1.0');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('created_at', datetime('now'));
INSERT OR IGNORE INTO metadata (key, value) VALUES ('node_count', '0');
INSERT OR IGNORE INTO metadata (key, value) VALUES ('edge_count', '0');
