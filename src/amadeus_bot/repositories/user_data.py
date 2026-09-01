from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


@dataclass(frozen=True, slots=True)
class DDLRecord:
    ddl_id: int
    content: str
    deadline_utc: str
    reminder_at_utc: str | None
    status: str
    created_at_utc: str
    reminder_sent_at_utc: str | None = None


class UserDataRepository:
    def __init__(self, users_root: Path) -> None:
        self.users_root = users_root
        self._lock = RLock()

    def add_ddl(
        self,
        user_id: str,
        content: str,
        deadline_utc: str,
        reminder_at_utc: str | None,
        created_at_utc: str,
    ) -> DDLRecord:
        with self._connection(user_id) as connection:
            cursor = connection.execute(
                """
                INSERT INTO ddl(content, deadline_utc, reminder_at_utc, created_at_utc, updated_at_utc)
                VALUES (?, ?, ?, ?, ?)
                """,
                (content, deadline_utc, reminder_at_utc, created_at_utc, created_at_utc),
            )
            ddl_id = int(cursor.lastrowid)
        result = self.get_ddl(user_id, ddl_id)
        if result is None:
            raise RuntimeError("DDL 写入后无法读取")
        return result

    def get_ddl(self, user_id: str, ddl_id: int) -> DDLRecord | None:
        with self._connection(user_id) as connection:
            row = connection.execute(
                "SELECT * FROM ddl WHERE ddl_id=? AND deleted_at_utc IS NULL", (int(ddl_id),)
            ).fetchone()
        return self._from_row(row) if row else None

    def list_ddl(self, user_id: str, status: str = "todo") -> list[DDLRecord]:
        where = "deleted_at_utc IS NULL"
        parameters: list[object] = []
        if status == "todo":
            where += " AND status='todo'"
        elif status == "done":
            where += " AND status='done'"
        elif status != "all":
            raise ValueError("status 必须是 todo、done 或 all")
        with self._connection(user_id) as connection:
            rows = connection.execute(
                f"SELECT * FROM ddl WHERE {where} ORDER BY deadline_utc, ddl_id", parameters
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def mark_done(self, user_id: str, ddl_id: int, updated_at_utc: str) -> bool:
        with self._connection(user_id) as connection:
            cursor = connection.execute(
                """
                UPDATE ddl SET status='done', reminder_at_utc=NULL, updated_at_utc=?
                WHERE ddl_id=? AND status='todo' AND deleted_at_utc IS NULL
                """,
                (updated_at_utc, int(ddl_id)),
            )
            return cursor.rowcount > 0

    def edit_ddl(
        self,
        user_id: str,
        ddl_id: int,
        *,
        content: str | None,
        deadline_utc: str | None,
        reminder_at_utc: str | None,
        updated_at_utc: str,
    ) -> bool:
        assignments = ["updated_at_utc=?", "reminder_sent_at_utc=NULL"]
        parameters: list[object] = [updated_at_utc]
        if content is not None:
            assignments.append("content=?")
            parameters.append(content)
        if deadline_utc is not None:
            assignments.extend(("deadline_utc=?", "reminder_at_utc=?"))
            parameters.extend((deadline_utc, reminder_at_utc))
        parameters.extend((int(ddl_id),))
        with self.connection(user_id) as connection:
            cursor = connection.execute(
                f"UPDATE ddl SET {', '.join(assignments)} "
                "WHERE ddl_id=? AND status='todo' AND deleted_at_utc IS NULL",
                parameters,
            )
            return cursor.rowcount > 0

    def due_reminders(self, now_utc: str) -> list[tuple[str, DDLRecord]]:
        result: list[tuple[str, DDLRecord]] = []
        if not self.users_root.exists():
            return result
        for user_dir in self.users_root.iterdir():
            if not user_dir.is_dir() or not user_dir.name.isdigit():
                continue
            with self.connection(user_dir.name) as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM ddl
                    WHERE status='todo' AND deleted_at_utc IS NULL
                      AND reminder_at_utc IS NOT NULL AND reminder_at_utc<=?
                      AND reminder_sent_at_utc IS NULL
                    ORDER BY reminder_at_utc LIMIT 20
                    """,
                    (now_utc,),
                ).fetchall()
            result.extend((user_dir.name, self._from_row(row)) for row in rows)
        return result

    def mark_reminder_sent(self, user_id: str, ddl_id: int, sent_at_utc: str) -> bool:
        with self.connection(user_id) as connection:
            cursor = connection.execute(
                """
                UPDATE ddl SET reminder_sent_at_utc=?
                WHERE ddl_id=? AND reminder_sent_at_utc IS NULL AND deleted_at_utc IS NULL
                """,
                (sent_at_utc, int(ddl_id)),
            )
            return cursor.rowcount > 0

    def set_reminder(
        self,
        user_id: str,
        ddl_id: int,
        reminder_at_utc: str | None,
        updated_at_utc: str,
    ) -> bool:
        with self._connection(user_id) as connection:
            cursor = connection.execute(
                """
                UPDATE ddl SET reminder_at_utc=?, updated_at_utc=?
                WHERE ddl_id=? AND status='todo' AND deleted_at_utc IS NULL
                """,
                (reminder_at_utc, updated_at_utc, int(ddl_id)),
            )
            return cursor.rowcount > 0

    def soft_delete(self, user_id: str, ddl_id: int, deleted_at_utc: str) -> bool:
        with self._connection(user_id) as connection:
            cursor = connection.execute(
                """
                UPDATE ddl SET deleted_at_utc=?, reminder_at_utc=NULL, updated_at_utc=?
                WHERE ddl_id=? AND deleted_at_utc IS NULL
                """,
                (deleted_at_utc, deleted_at_utc, int(ddl_id)),
            )
            return cursor.rowcount > 0

    @contextmanager
    def connection(self, user_id: str) -> Iterator[sqlite3.Connection]:
        normalized = str(user_id)
        if not normalized.isdigit():
            raise ValueError("user_id 必须是纯数字 QQ 号")
        with self._lock:
            user_dir = self.users_root / normalized
            user_dir.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(user_dir / "user.sqlite3", timeout=5.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")
            connection.executescript(_USER_SCHEMA)
            columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(ddl)")}
            if "reminder_sent_at_utc" not in columns:
                connection.execute("ALTER TABLE ddl ADD COLUMN reminder_sent_at_utc TEXT")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

    _connection = connection

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DDLRecord:
        return DDLRecord(
            ddl_id=int(row["ddl_id"]),
            content=str(row["content"]),
            deadline_utc=str(row["deadline_utc"]),
            reminder_at_utc=str(row["reminder_at_utc"]) if row["reminder_at_utc"] else None,
            status=str(row["status"]),
            created_at_utc=str(row["created_at_utc"]),
            reminder_sent_at_utc=(
                str(row["reminder_sent_at_utc"])
                if "reminder_sent_at_utc" in row.keys() and row["reminder_sent_at_utc"]
                else None
            ),
        )


_USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS ddl (
    ddl_id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    deadline_utc TEXT NOT NULL,
    reminder_at_utc TEXT,
    status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo', 'done')),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    deleted_at_utc TEXT
    ,reminder_sent_at_utc TEXT
);
CREATE INDEX IF NOT EXISTS idx_ddl_deadline ON ddl(status, deadline_utc, deleted_at_utc);

CREATE TABLE IF NOT EXISTS memories (
    memory_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    evidence_message_ids TEXT NOT NULL DEFAULT '[]',
    confidence REAL NOT NULL DEFAULT 0.5,
    sensitivity TEXT NOT NULL DEFAULT 'normal',
    source_group_id TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    version INTEGER NOT NULL DEFAULT 1,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at_utc TEXT
);
CREATE TABLE IF NOT EXISTS user_preferences (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    teacher TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL DEFAULT '',
    weekday INTEGER NOT NULL CHECK(weekday BETWEEN 1 AND 7),
    start_section INTEGER NOT NULL,
    end_section INTEGER NOT NULL,
    weeks TEXT NOT NULL,
    campus TEXT NOT NULL DEFAULT '',
    reminder_minutes INTEGER,
    source TEXT NOT NULL DEFAULT 'manual',
    import_batch_id TEXT,
    created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at_utc TEXT
);
CREATE INDEX IF NOT EXISTS idx_courses_weekday ON courses(weekday, deleted_at_utc);
CREATE TABLE IF NOT EXISTS course_reminder_deliveries (
    course_id INTEGER NOT NULL,
    occurrence_date TEXT NOT NULL,
    sent_at_utc TEXT NOT NULL,
    PRIMARY KEY(course_id, occurrence_date)
);
"""
