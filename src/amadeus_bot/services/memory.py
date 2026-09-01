from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from amadeus_bot.repositories.user_data import UserDataRepository


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: int
    category: str
    content: str
    confidence: float
    sensitivity: str
    source_group_id: str | None
    status: str
    version: int


class MemoryService:
    def __init__(self, repository: UserDataRepository) -> None:
        self.repository = repository

    def analysis_enabled(self, user_id: str) -> bool:
        with self.repository.connection(user_id) as connection:
            row = connection.execute(
                "SELECT value FROM user_preferences WHERE key='personality_analysis'"
            ).fetchone()
        return row is None or str(row["value"]).lower() != "off"

    def set_analysis(self, user_id: str, enabled: bool) -> None:
        self._set_preference(user_id, "personality_analysis", "on" if enabled else "off")

    def logging_enabled(self, user_id: str) -> bool:
        with self.repository.connection(user_id) as connection:
            row = connection.execute(
                "SELECT value FROM user_preferences WHERE key='message_logging'"
            ).fetchone()
        return row is None or str(row["value"]).lower() != "off"

    def set_logging(self, user_id: str, enabled: bool) -> None:
        self._set_preference(user_id, "message_logging", "on" if enabled else "off")

    def _set_preference(self, user_id: str, key: str, value: str) -> None:
        with self.repository.connection(user_id) as connection:
            connection.execute(
                """
                INSERT INTO user_preferences(key,value,updated_at_utc) VALUES (?,?,?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at_utc=excluded.updated_at_utc
                """,
                (key, value, datetime.now(UTC).isoformat()),
            )

    def list(self, user_id: str, memory_id: int | None = None) -> list[MemoryRecord]:
        with self.repository.connection(user_id) as connection:
            if memory_id is None:
                rows = connection.execute(
                    "SELECT * FROM memories WHERE status='active' ORDER BY memory_id"
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM memories WHERE memory_id=? AND status='active'", (memory_id,)
                ).fetchall()
        return [self._from_row(row) for row in rows]

    def add_candidate(
        self,
        user_id: str,
        category: str,
        content: str,
        *,
        confidence: float,
        source_group_id: str | None,
        evidence_message_ids: tuple[str, ...] = (),
        sensitivity: str = "normal",
    ) -> int:
        if not self.analysis_enabled(user_id):
            raise ValueError("该用户已退出性格分析")
        if sensitivity != "normal":
            raise ValueError("敏感信息不会自动写入记忆")
        with self.repository.connection(user_id) as connection:
            duplicate = connection.execute(
                "SELECT memory_id FROM memories WHERE status='active' AND category=? AND content=?",
                (category, content.strip()),
            ).fetchone()
            if duplicate:
                return int(duplicate["memory_id"])
            cursor = connection.execute(
                """
                INSERT INTO memories(
                    category,content,evidence_message_ids,confidence,sensitivity,source_group_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    category,
                    content.strip(),
                    json.dumps(evidence_message_ids, ensure_ascii=False),
                    max(0.0, min(1.0, confidence)),
                    sensitivity,
                    source_group_id,
                ),
            )
            return int(cursor.lastrowid)

    def edit(self, user_id: str, memory_id: int, content: str) -> bool:
        with self.repository.connection(user_id) as connection:
            cursor = connection.execute(
                """
                UPDATE memories SET content=?,version=version+1,updated_at_utc=?
                WHERE memory_id=? AND status='active'
                """,
                (content.strip(), datetime.now(UTC).isoformat(), int(memory_id)),
            )
            return cursor.rowcount > 0

    def delete(self, user_id: str, memory_id: int) -> bool:
        with self.repository.connection(user_id) as connection:
            cursor = connection.execute(
                """
                UPDATE memories SET status='deleted',version=version+1,updated_at_utc=?
                WHERE memory_id=? AND status='active'
                """,
                (datetime.now(UTC).isoformat(), int(memory_id)),
            )
            return cursor.rowcount > 0

    @staticmethod
    def _from_row(row) -> MemoryRecord:
        return MemoryRecord(
            memory_id=int(row["memory_id"]),
            category=str(row["category"]),
            content=str(row["content"]),
            confidence=float(row["confidence"]),
            sensitivity=str(row["sensitivity"]),
            source_group_id=str(row["source_group_id"]) if row["source_group_id"] else None,
            status=str(row["status"]),
            version=int(row["version"]),
        )
