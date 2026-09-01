from __future__ import annotations

import json
import random
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from threading import RLock


@dataclass(frozen=True, slots=True)
class WifePair:
    user_id: str
    partner_id: str
    business_date: str
    changes: int


@dataclass(frozen=True, slots=True)
class QuoteRecord:
    quote_id: int
    source_message_id: str
    source_author_id: str
    saved_by_id: str
    name: str
    tags: tuple[str, ...]
    text: str
    media_refs: tuple[dict[str, str], ...]
    created_at: str


class GroupDataRepository:
    def __init__(self, groups_root: Path) -> None:
        self.groups_root = groups_root
        self._lock = RLock()

    @contextmanager
    def connection(self, group_id: str) -> Iterator[sqlite3.Connection]:
        normalized = str(group_id)
        if not normalized.isdigit():
            raise ValueError("group_id 必须是纯数字群号")
        with self._lock:
            directory = self.groups_root / normalized
            directory.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(directory / "group.sqlite3", timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.executescript(_GROUP_SCHEMA)
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    def get_wife(self, group_id: str, user_id: str, business_date: date) -> WifePair | None:
        with self.connection(group_id) as connection:
            row = connection.execute(
                "SELECT * FROM wife_pairs WHERE business_date=? AND user_id=?",
                (business_date.isoformat(), str(user_id)),
            ).fetchone()
        return self._wife_from_row(row) if row else None

    def assign_wife(
        self,
        group_id: str,
        user_id: str,
        candidates: list[str],
        business_date: date,
        *,
        replace: bool = False,
        max_changes: int = 2,
    ) -> WifePair:
        user_id = str(user_id)
        today = business_date.isoformat()
        with self.connection(group_id) as connection:
            current = connection.execute(
                "SELECT * FROM wife_pairs WHERE business_date=? AND user_id=?", (today, user_id)
            ).fetchone()
            changes = int(current["changes"]) if current else 0
            if current and not replace:
                return self._wife_from_row(current)
            if current and changes >= max_changes:
                raise ValueError("今日更换次数已用完")
            old_partner = str(current["partner_id"]) if current else None
            if old_partner:
                connection.execute(
                    "DELETE FROM wife_pairs WHERE business_date=? AND user_id IN (?, ?)",
                    (today, user_id, old_partner),
                )
            occupied = {
                str(row[0])
                for row in connection.execute(
                    "SELECT user_id FROM wife_pairs WHERE business_date=?", (today,)
                ).fetchall()
            }
            eligible = [
                str(candidate)
                for candidate in candidates
                if str(candidate) != user_id
                and str(candidate) != old_partner
                and str(candidate) not in occupied
            ]
            if not eligible:
                raise ValueError("当前没有可配对的群友")
            partner = random.choice(eligible)
            new_changes = changes + (1 if current else 0)
            connection.executemany(
                """
                INSERT OR REPLACE INTO wife_pairs(
                    business_date, user_id, partner_id, changes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                ((today, user_id, partner, new_changes), (today, partner, user_id, 0)),
            )
        return WifePair(user_id, partner, today, new_changes)

    def marry(self, group_id: str, user_id: str, partner_id: str, business_date: date) -> WifePair:
        user_id, partner_id = str(user_id), str(partner_id)
        if user_id == partner_id:
            raise ValueError("不能和自己结婚")
        today = business_date.isoformat()
        with self.connection(group_id) as connection:
            occupied = connection.execute(
                "SELECT user_id FROM wife_pairs WHERE business_date=? AND user_id IN (?, ?)",
                (today, user_id, partner_id),
            ).fetchone()
            if occupied:
                raise ValueError("其中一人今天已有配对")
            connection.executemany(
                """
                INSERT INTO wife_pairs(business_date,user_id,partner_id,changes)
                VALUES (?, ?, ?, 0)
                """,
                ((today, user_id, partner_id), (today, partner_id, user_id)),
            )
        return WifePair(user_id, partner_id, today, 0)

    def add_quote(
        self,
        group_id: str,
        source_message_id: str,
        source_author_id: str,
        saved_by_id: str,
        name: str,
        tags: tuple[str, ...],
        text: str,
        media_refs: tuple[dict[str, str], ...] = (),
    ) -> QuoteRecord:
        with self.connection(group_id) as connection:
            existing = connection.execute(
                "SELECT quote_id FROM quotes WHERE source_message_id=? AND deleted_at IS NULL",
                (str(source_message_id),),
            ).fetchone()
            if existing:
                raise ValueError(f"该消息已收藏为语录 #{existing['quote_id']}")
            cursor = connection.execute(
                """
                INSERT INTO quotes(
                    source_message_id,source_author_id,saved_by_id,name,tags,text,media_refs
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(source_message_id),
                    str(source_author_id),
                    str(saved_by_id),
                    name,
                    json.dumps(tags, ensure_ascii=False),
                    text,
                    json.dumps(media_refs, ensure_ascii=False),
                ),
            )
            quote_id = int(cursor.lastrowid)
        result = self.get_quote(group_id, quote_id)
        if result is None:
            raise RuntimeError("语录写入后无法读取")
        return result

    def get_quote(self, group_id: str, quote_id: int) -> QuoteRecord | None:
        with self.connection(group_id) as connection:
            row = connection.execute(
                "SELECT * FROM quotes WHERE quote_id=? AND deleted_at IS NULL", (int(quote_id),)
            ).fetchone()
        return self._quote_from_row(row) if row else None

    def list_quotes(self, group_id: str, query: str = "") -> list[QuoteRecord]:
        with self.connection(group_id) as connection:
            if query:
                pattern = f"%{query}%"
                rows = connection.execute(
                    """
                    SELECT * FROM quotes WHERE deleted_at IS NULL AND
                    (text LIKE ? OR name LIKE ? OR tags LIKE ? OR source_author_id=?)
                    ORDER BY quote_id DESC
                    """,
                    (pattern, pattern, pattern, query.lstrip("@")),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM quotes WHERE deleted_at IS NULL ORDER BY quote_id DESC"
                ).fetchall()
        return [self._quote_from_row(row) for row in rows]

    def random_quote(self, group_id: str, query: str = "") -> QuoteRecord | None:
        rows = self.list_quotes(group_id, query)
        return random.choice(rows) if rows else None

    def edit_quote(self, group_id: str, quote_id: int, name: str, tags: tuple[str, ...]) -> bool:
        with self.connection(group_id) as connection:
            cursor = connection.execute(
                """
                UPDATE quotes SET name=?, tags=?, updated_at=CURRENT_TIMESTAMP
                WHERE quote_id=? AND deleted_at IS NULL
                """,
                (name, json.dumps(tags, ensure_ascii=False), int(quote_id)),
            )
            return cursor.rowcount > 0

    def delete_quote(self, group_id: str, quote_id: int) -> bool:
        with self.connection(group_id) as connection:
            cursor = connection.execute(
                "UPDATE quotes SET deleted_at=CURRENT_TIMESTAMP WHERE quote_id=? AND deleted_at IS NULL",
                (int(quote_id),),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _wife_from_row(row: sqlite3.Row) -> WifePair:
        return WifePair(
            str(row["user_id"]),
            str(row["partner_id"]),
            str(row["business_date"]),
            int(row["changes"]),
        )

    @staticmethod
    def _quote_from_row(row: sqlite3.Row) -> QuoteRecord:
        return QuoteRecord(
            int(row["quote_id"]),
            str(row["source_message_id"]),
            str(row["source_author_id"]),
            str(row["saved_by_id"]),
            str(row["name"]),
            tuple(json.loads(row["tags"] or "[]")),
            str(row["text"]),
            tuple(json.loads(row["media_refs"] or "[]")),
            str(row["created_at"]),
        )


_GROUP_SCHEMA = """
CREATE TABLE IF NOT EXISTS wife_pairs (
    business_date TEXT NOT NULL,
    user_id TEXT NOT NULL,
    partner_id TEXT NOT NULL,
    changes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(business_date, user_id)
);
CREATE TABLE IF NOT EXISTS quotes (
    quote_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_message_id TEXT NOT NULL,
    source_author_id TEXT NOT NULL,
    saved_by_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '[]',
    text TEXT NOT NULL DEFAULT '',
    media_refs TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_quotes_source
ON quotes(source_message_id) WHERE deleted_at IS NULL;
"""
