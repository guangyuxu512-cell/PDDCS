PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS shops (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    platform            TEXT NOT NULL CHECK(platform IN ('pdd','douyin','qianniu')),
    username            TEXT NOT NULL DEFAULT '',
    password            TEXT NOT NULL DEFAULT '',
    is_online           INTEGER NOT NULL DEFAULT 0,
    ai_enabled          INTEGER NOT NULL DEFAULT 0,
    cookie_valid        INTEGER NOT NULL DEFAULT 0,
    cookie_last_refresh TEXT NOT NULL DEFAULT '',
    today_served_count  INTEGER NOT NULL DEFAULT 0,
    last_active_at      TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS shop_configs (
    shop_id                 TEXT PRIMARY KEY REFERENCES shops(id) ON DELETE CASCADE,
    llm_mode                TEXT NOT NULL DEFAULT 'global' CHECK(llm_mode IN ('global','custom')),
    custom_api_key          TEXT DEFAULT '',
    custom_model            TEXT DEFAULT '',
    reply_style_note        TEXT DEFAULT '',
    knowledge_paths         TEXT NOT NULL DEFAULT '[]',
    use_global_knowledge    INTEGER NOT NULL DEFAULT 1,
    human_agent_name        TEXT NOT NULL DEFAULT '',
    escalation_rules        TEXT NOT NULL DEFAULT '[]',
    escalation_fallback_msg TEXT NOT NULL DEFAULT '',
    updated_at              TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS sessions (
    id                   TEXT PRIMARY KEY,
    shop_id              TEXT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    shop_name            TEXT NOT NULL DEFAULT '',
    platform             TEXT NOT NULL CHECK(platform IN ('pdd','douyin','qianniu')),
    buyer_id             TEXT NOT NULL,
    buyer_name           TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'ai_processing' CHECK(status IN ('ai_processing','escalated','closed')),
    last_message_preview TEXT NOT NULL DEFAULT '',
    updated_at           TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    created_at           TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_sessions_shop_id ON sessions(shop_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);

CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    sender      TEXT NOT NULL CHECK(sender IN ('buyer','ai','human')),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    dedup_key   TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_dedup_key ON messages(dedup_key);

CREATE TABLE IF NOT EXISTS knowledge_files (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    path        TEXT UNIQUE NOT NULL,
    node_type   TEXT NOT NULL CHECK(node_type IN ('folder','file')),
    parent_path TEXT DEFAULT NULL,
    content     TEXT NOT NULL DEFAULT '',
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS system_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

INSERT OR IGNORE INTO system_settings (key, value) VALUES
    ('apiBaseUrl',           ''),
    ('apiKey',               ''),
    ('defaultModel',         ''),
    ('temperature',          '0.7'),
    ('maxTokens',            '200'),
    ('defaultFallbackMsg',   ''),
    ('defaultKeywords',      '[]'),
    ('logLevel',             'INFO'),
    ('historyRetentionDays', '30'),
    ('alertWebhookUrl',      ''),
    ('maxShops',             '10');

CREATE TABLE IF NOT EXISTS escalation_logs (
    id                 TEXT PRIMARY KEY,
    session_id         TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    shop_id            TEXT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    trigger_rule_type  TEXT NOT NULL,
    trigger_rule_value TEXT NOT NULL DEFAULT '',
    matched_content    TEXT NOT NULL DEFAULT '',
    target_agent       TEXT NOT NULL DEFAULT '',
    success            INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_escalation_logs_shop_id ON escalation_logs(shop_id);
CREATE INDEX IF NOT EXISTS idx_escalation_logs_created_at ON escalation_logs(created_at);
