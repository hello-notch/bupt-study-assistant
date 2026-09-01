from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any


class CoreDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = RLock()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(_SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def execute(self, sql: str, parameters: Sequence[Any] = ()) -> int:
        with self.connection() as connection:
            cursor = connection.execute(sql, parameters)
            return cursor.lastrowid

    def fetch_one(self, sql: str, parameters: Sequence[Any] = ()) -> sqlite3.Row | None:
        with self.connection() as connection:
            return connection.execute(sql, parameters).fetchone()

    def fetch_all(self, sql: str, parameters: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self.connection() as connection:
            return list(connection.execute(sql, parameters).fetchall())


_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO schema_version(version) VALUES (1);

CREATE TABLE IF NOT EXISTS members (
    user_id TEXT PRIMARY KEY,
    added_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feature_flags (
    feature TEXT NOT NULL,
    scope_type TEXT NOT NULL CHECK(scope_type IN ('global', 'group')),
    scope_id TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(feature, scope_type, scope_id)
);

CREATE TABLE IF NOT EXISTS ignore_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    scope_type TEXT NOT NULL CHECK(scope_type IN ('global', 'group')),
    scope_id TEXT NOT NULL DEFAULT '',
    exclude_ai INTEGER NOT NULL DEFAULT 1,
    exclude_stats INTEGER NOT NULL DEFAULT 1,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, scope_type, scope_id)
);

CREATE TABLE IF NOT EXISTS recommendations (
    recommendation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pool TEXT NOT NULL CHECK(pool IN ('activity', 'food', 'music')),
    path TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1 CHECK(weight > 0),
    tags TEXT NOT NULL DEFAULT '',
    creator_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_recommendations_pool ON recommendations(pool, enabled, deleted_at);

CREATE TABLE IF NOT EXISTS ai_usage (
    usage_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL,
    success INTEGER NOT NULL CHECK(success IN (0, 1)),
    group_id TEXT,
    user_id TEXT,
    error_type TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_created_at ON ai_usage(created_at);

CREATE TABLE IF NOT EXISTS ai_quotas (
    task TEXT PRIMARY KEY,
    daily_limit INTEGER NOT NULL CHECK(daily_limit >= 0),
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    conversation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_key TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    user_id TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_conversation_scope ON conversation_messages(scope_key, conversation_id);

CREATE TABLE IF NOT EXISTS command_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    command TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    subject_user_id TEXT,
    group_id TEXT,
    status TEXT NOT NULL,
    parameter_summary TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_command_audit_trace ON command_audit(trace_id);

CREATE TABLE IF NOT EXISTS subscriptions (
    source TEXT NOT NULL,
    scope_type TEXT NOT NULL CHECK(scope_type IN ('user', 'group')),
    scope_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    filters TEXT NOT NULL DEFAULT '{}',
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(source, scope_type, scope_id)
);

CREATE TABLE IF NOT EXISTS source_health (
    source TEXT PRIMARY KEY,
    last_success_at TEXT,
    last_failure_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    item_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT NOT NULL DEFAULT '',
    trace_id TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS source_items (
    source TEXT NOT NULL,
    item_id TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT,
    department TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    content_hash TEXT NOT NULL DEFAULT '',
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(source, item_id)
);
CREATE INDEX IF NOT EXISTS idx_source_items_time ON source_items(source, published_at DESC);

CREATE TABLE IF NOT EXISTS memory_change_requests (
    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    request_type TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    handled_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handled_at TEXT
);

CREATE TABLE IF NOT EXISTS runtime_errors (
    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    trace_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS media_descriptions (
    media_hash TEXT PRIMARY KEY,
    media_type TEXT NOT NULL,
    description TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS scheduler_deliveries (
    delivery_key TEXT PRIMARY KEY,
    delivered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
