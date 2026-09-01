from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from amadeus_bot.repositories.database import CoreDatabase


@dataclass(frozen=True, slots=True)
class Recommendation:
    recommendation_id: int
    pool: str
    path: str
    content: str
    weight: float
    tags: tuple[str, ...]
    creator_id: str


class CoreRepository:
    def __init__(self, database: CoreDatabase) -> None:
        self.database = database

    def is_member(self, user_id: str) -> bool:
        return self.database.fetch_one("SELECT 1 FROM members WHERE user_id=?", (str(user_id),)) is not None

    def add_member(self, user_id: str, added_by: str) -> None:
        self.database.execute(
            "INSERT OR REPLACE INTO members(user_id, added_by, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (str(user_id), str(added_by)),
        )

    def remove_member(self, user_id: str) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute("DELETE FROM members WHERE user_id=?", (str(user_id),))
            return cursor.rowcount > 0

    def list_members(self) -> list[str]:
        rows = self.database.fetch_all("SELECT user_id FROM members ORDER BY user_id")
        return [str(row["user_id"]) for row in rows]

    def set_feature(self, feature: str, scope_type: str, scope_id: str, enabled: bool, actor: str) -> None:
        self.database.execute(
            """
            INSERT INTO feature_flags(feature, scope_type, scope_id, enabled, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(feature, scope_type, scope_id) DO UPDATE SET
                enabled=excluded.enabled, updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP
            """,
            (feature, scope_type, scope_id, int(enabled), actor),
        )

    def reset_group_feature(self, feature: str, group_id: str) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "DELETE FROM feature_flags WHERE feature=? AND scope_type='group' AND scope_id=?",
                (feature, str(group_id)),
            )
            return cursor.rowcount > 0

    def get_feature_rows(self, feature: str | None = None) -> list[dict[str, Any]]:
        if feature:
            rows = self.database.fetch_all(
                "SELECT * FROM feature_flags WHERE feature=? ORDER BY scope_type, scope_id", (feature,)
            )
        else:
            rows = self.database.fetch_all(
                "SELECT * FROM feature_flags ORDER BY feature, scope_type, scope_id"
            )
        return [dict(row) for row in rows]

    def add_ignore_rule(
        self,
        user_id: str,
        scope_type: str,
        scope_id: str,
        actor: str,
        *,
        exclude_ai: bool = True,
        exclude_stats: bool = True,
    ) -> int:
        return self.database.execute(
            """
            INSERT INTO ignore_rules(user_id, scope_type, scope_id, exclude_ai, exclude_stats, created_by)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, scope_type, scope_id) DO UPDATE SET
                exclude_ai=excluded.exclude_ai, exclude_stats=excluded.exclude_stats,
                created_by=excluded.created_by, created_at=CURRENT_TIMESTAMP
            """,
            (str(user_id), scope_type, scope_id, int(exclude_ai), int(exclude_stats), str(actor)),
        )

    def delete_ignore_rule(self, rule_id: int) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute("DELETE FROM ignore_rules WHERE rule_id=?", (int(rule_id),))
            return cursor.rowcount > 0

    def list_ignore_rules(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self.database.fetch_all("SELECT * FROM ignore_rules ORDER BY rule_id")]

    def is_ignored(self, user_id: str, group_id: str | None, kind: str) -> bool:
        column = "exclude_ai" if kind == "ai" else "exclude_stats"
        rows = self.database.fetch_all(
            f"""
            SELECT {column} AS excluded FROM ignore_rules
            WHERE user_id=? AND (
                scope_type='global' OR (scope_type='group' AND scope_id=?)
            )
            """,
            (str(user_id), str(group_id or "")),
        )
        return any(bool(row["excluded"]) for row in rows)

    def add_recommendation(
        self,
        pool: str,
        path: str,
        content: str,
        weight: float,
        tags: tuple[str, ...],
        creator_id: str,
    ) -> int:
        return self.database.execute(
            """
            INSERT INTO recommendations(pool, path, content, weight, tags, creator_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (pool, path, content, weight, json.dumps(tags, ensure_ascii=False), str(creator_id)),
        )

    def list_recommendations(self, pool: str, path: str = "") -> list[Recommendation]:
        sql = """
            SELECT * FROM recommendations
            WHERE pool=? AND enabled=1 AND deleted_at IS NULL
        """
        parameters: list[Any] = [pool]
        if path:
            sql += " AND path=?"
            parameters.append(path)
        sql += " ORDER BY recommendation_id"
        return [self._recommendation_from_row(row) for row in self.database.fetch_all(sql, parameters)]

    def choose_recommendation(self, pool: str, path: str = "") -> Recommendation | None:
        items = self.list_recommendations(pool, path)
        if not items:
            return None
        return random.choices(items, weights=[item.weight for item in items], k=1)[0]

    def delete_recommendation(self, recommendation_id: int) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE recommendations SET deleted_at=CURRENT_TIMESTAMP
                WHERE recommendation_id=? AND deleted_at IS NULL
                """,
                (int(recommendation_id),),
            )
            return cursor.rowcount > 0

    def get_recommendation(self, recommendation_id: int) -> Recommendation | None:
        row = self.database.fetch_one(
            "SELECT * FROM recommendations WHERE recommendation_id=? AND deleted_at IS NULL",
            (int(recommendation_id),),
        )
        return self._recommendation_from_row(row) if row else None

    def record_ai_usage(self, **values: Any) -> None:
        self.database.execute(
            """
            INSERT INTO ai_usage(
                task, provider, model, input_tokens, output_tokens, cached_tokens,
                latency_ms, success, group_id, user_id, error_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["task"],
                values["provider"],
                values["model"],
                values.get("input_tokens", 0),
                values.get("output_tokens", 0),
                values.get("cached_tokens", 0),
                values["latency_ms"],
                int(values["success"]),
                values.get("group_id"),
                values.get("user_id"),
                values.get("error_type"),
            ),
        )

    def ai_usage_summary(self, days: int) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            """
            SELECT provider, model, task, COUNT(*) AS calls,
                   SUM(input_tokens) AS input_tokens, SUM(output_tokens) AS output_tokens,
                   CAST(AVG(latency_ms) AS INTEGER) AS avg_latency_ms,
                   SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) AS failures
            FROM ai_usage
            WHERE created_at >= datetime('now', ?)
            GROUP BY provider, model, task
            ORDER BY calls DESC
            """,
            (f"-{int(days)} days",),
        )
        return [dict(row) for row in rows]

    def set_ai_quota(self, task: str, daily_limit: int, actor: str) -> None:
        self.database.execute(
            """
            INSERT INTO ai_quotas(task, daily_limit, updated_by, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(task) DO UPDATE SET
                daily_limit=excluded.daily_limit, updated_by=excluded.updated_by,
                updated_at=CURRENT_TIMESTAMP
            """,
            (task, int(daily_limit), str(actor)),
        )

    def ai_quota_status(self) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            """
            SELECT q.task, q.daily_limit, q.updated_at,
                   COALESCE(u.used_today, 0) AS used_today
            FROM ai_quotas q
            LEFT JOIN (
                SELECT task, COUNT(*) AS used_today FROM ai_usage
                WHERE success=1 AND date(created_at)=date('now') GROUP BY task
            ) u ON u.task=q.task
            ORDER BY q.task
            """
        )
        return [dict(row) for row in rows]

    def ai_quota_for_task(self, task: str) -> tuple[int, int] | None:
        row = self.database.fetch_one(
            """
            SELECT q.daily_limit,
                   (SELECT COUNT(*) FROM ai_usage u
                    WHERE u.task=q.task AND u.success=1 AND date(u.created_at)=date('now')) AS used_today
            FROM ai_quotas q WHERE q.task=?
            """,
            (task,),
        )
        if row is None:
            return None
        return int(row["daily_limit"]), int(row["used_today"])

    def append_conversation(self, scope_key: str, role: str, content: str, user_id: str | None) -> None:
        self.database.execute(
            "INSERT INTO conversation_messages(scope_key, role, content, user_id) VALUES (?, ?, ?, ?)",
            (scope_key, role, content, user_id),
        )

    def recent_conversation(self, scope_key: str, limit: int = 12) -> list[dict[str, str]]:
        rows = self.database.fetch_all(
            """
            SELECT role, content FROM (
                SELECT conversation_id, role, content FROM conversation_messages
                WHERE scope_key=? ORDER BY conversation_id DESC LIMIT ?
            ) ORDER BY conversation_id
            """,
            (scope_key, int(limit)),
        )
        return [{"role": str(row["role"]), "content": str(row["content"])} for row in rows]

    def record_audit(
        self,
        trace_id: str,
        command: str,
        requested_by: str,
        status: str,
        *,
        subject_user_id: str | None = None,
        group_id: str | None = None,
        parameter_summary: str = "",
    ) -> int:
        return self.database.execute(
            """
            INSERT INTO command_audit(
                trace_id, command, requested_by, subject_user_id, group_id, status, parameter_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                command,
                str(requested_by),
                subject_user_id,
                group_id,
                status,
                parameter_summary[:500],
            ),
        )

    def set_subscription(
        self,
        source: str,
        scope_type: str,
        scope_id: str,
        enabled: bool,
        actor: str,
        filters: dict[str, Any] | None = None,
    ) -> None:
        self.database.execute(
            """
            INSERT INTO subscriptions(source,scope_type,scope_id,enabled,filters,updated_by)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source,scope_type,scope_id) DO UPDATE SET
                enabled=excluded.enabled, filters=excluded.filters,
                updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP
            """,
            (
                source,
                scope_type,
                str(scope_id),
                int(enabled),
                json.dumps(filters or {}, ensure_ascii=False),
                actor,
            ),
        )

    def list_subscriptions(self, source: str | None = None) -> list[dict[str, Any]]:
        if source:
            rows = self.database.fetch_all(
                "SELECT * FROM subscriptions WHERE source=? ORDER BY scope_type,scope_id", (source,)
            )
        else:
            rows = self.database.fetch_all("SELECT * FROM subscriptions ORDER BY source,scope_type,scope_id")
        return [dict(row) for row in rows]

    def upsert_source_item(self, source: str, item: dict[str, Any]) -> bool:
        existed = (
            self.database.fetch_one(
                "SELECT 1 FROM source_items WHERE source=? AND item_id=?", (source, str(item["item_id"]))
            )
            is not None
        )
        self.database.execute(
            """
            INSERT INTO source_items(
                source,item_id,title,published_at,department,summary,url,metadata,content_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source,item_id) DO UPDATE SET
                title=excluded.title,published_at=excluded.published_at,
                department=excluded.department,summary=excluded.summary,url=excluded.url,
                metadata=excluded.metadata,content_hash=excluded.content_hash,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                source,
                str(item["item_id"]),
                item["title"],
                item.get("published_at"),
                item.get("department", ""),
                item.get("summary", ""),
                item.get("url", ""),
                json.dumps(item.get("metadata", {}), ensure_ascii=False),
                item.get("content_hash", ""),
            ),
        )
        return not existed

    def query_source_items(self, source: str, query: str = "", limit: int = 10) -> list[dict[str, Any]]:
        if query:
            pattern = f"%{query}%"
            rows = self.database.fetch_all(
                """
                SELECT * FROM source_items WHERE source=? AND
                (title LIKE ? OR summary LIKE ? OR department LIKE ?)
                ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT ?
                """,
                (source, pattern, pattern, pattern, int(limit)),
            )
        else:
            rows = self.database.fetch_all(
                """
                SELECT * FROM source_items WHERE source=?
                ORDER BY COALESCE(published_at, first_seen_at) DESC LIMIT ?
                """,
                (source, int(limit)),
            )
        return [dict(row) for row in rows]

    def set_source_health(
        self,
        source: str,
        *,
        success: bool,
        item_count: int = 0,
        error_summary: str = "",
        trace_id: str | None = None,
    ) -> None:
        self.database.execute(
            """
            INSERT INTO source_health(
                source,last_success_at,last_failure_at,consecutive_failures,item_count,error_summary,trace_id
            ) VALUES (
                ?, CASE WHEN ? THEN CURRENT_TIMESTAMP END, CASE WHEN ? THEN NULL ELSE CURRENT_TIMESTAMP END,
                CASE WHEN ? THEN 0 ELSE 1 END, ?, ?, ?
            )
            ON CONFLICT(source) DO UPDATE SET
                last_success_at=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE source_health.last_success_at END,
                last_failure_at=CASE WHEN ? THEN source_health.last_failure_at ELSE CURRENT_TIMESTAMP END,
                consecutive_failures=CASE WHEN ? THEN 0 ELSE source_health.consecutive_failures+1 END,
                item_count=excluded.item_count,error_summary=excluded.error_summary,
                trace_id=excluded.trace_id,updated_at=CURRENT_TIMESTAMP
            """,
            (
                source,
                success,
                success,
                success,
                int(item_count),
                error_summary[:300],
                trace_id,
                success,
                success,
                success,
            ),
        )

    def get_source_health(self, source: str) -> dict[str, Any] | None:
        row = self.database.fetch_one("SELECT * FROM source_health WHERE source=?", (source,))
        return dict(row) if row else None

    def prune_source_items(self, source: str, current_item_ids: list[str]) -> int:
        with self.database.connection() as connection:
            if not current_item_ids:
                cursor = connection.execute("DELETE FROM source_items WHERE source=?", (source,))
            else:
                placeholders = ",".join("?" for _ in current_item_ids)
                cursor = connection.execute(
                    f"DELETE FROM source_items WHERE source=? AND item_id NOT IN ({placeholders})",
                    (source, *current_item_ids),
                )
            return cursor.rowcount

    def create_memory_request(self, user_id: str, request_type: str, detail: str = "") -> int:
        return self.database.execute(
            "INSERT INTO memory_change_requests(user_id,request_type,detail) VALUES (?, ?, ?)",
            (str(user_id), request_type, detail[:500]),
        )

    def list_memory_requests(self, status: str = "pending") -> list[dict[str, Any]]:
        if status == "all":
            rows = self.database.fetch_all("SELECT * FROM memory_change_requests ORDER BY request_id DESC")
        else:
            rows = self.database.fetch_all(
                "SELECT * FROM memory_change_requests WHERE status=? ORDER BY request_id", (status,)
            )
        return [dict(row) for row in rows]

    def complete_memory_requests(self, user_id: str, actor: str) -> int:
        with self.database.connection() as connection:
            cursor = connection.execute(
                """
                UPDATE memory_change_requests SET status='completed',handled_by=?,handled_at=CURRENT_TIMESTAMP
                WHERE user_id=? AND status='pending'
                """,
                (actor, str(user_id)),
            )
            return cursor.rowcount

    def get_media_description(self, media_hash: str) -> str | None:
        row = self.database.fetch_one(
            "SELECT description FROM media_descriptions WHERE media_hash=?", (media_hash,)
        )
        return str(row["description"]) if row else None

    def save_media_description(self, media_hash: str, media_type: str, description: str, model: str) -> None:
        self.database.execute(
            """
            INSERT OR REPLACE INTO media_descriptions(media_hash,media_type,description,model)
            VALUES (?, ?, ?, ?)
            """,
            (media_hash, media_type, description[:2000], model),
        )

    def audit_trace(self, trace_id: str) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            "SELECT * FROM command_audit WHERE trace_id=? ORDER BY audit_id", (trace_id,)
        )
        return [dict(row) for row in rows]

    def record_error(self, category: str, summary: str, trace_id: str | None = None) -> int:
        return self.database.execute(
            "INSERT INTO runtime_errors(category,summary,trace_id) VALUES (?, ?, ?)",
            (category, summary[:500], trace_id),
        )

    def recent_errors(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            "SELECT * FROM runtime_errors ORDER BY error_id DESC LIMIT ?", (min(100, int(limit)),)
        )
        return [dict(row) for row in rows]

    def claim_delivery(self, delivery_key: str) -> bool:
        with self.database.connection() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO scheduler_deliveries(delivery_key) VALUES (?)", (delivery_key,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def _recommendation_from_row(row: Any) -> Recommendation:
        try:
            tags = tuple(json.loads(row["tags"]))
        except (json.JSONDecodeError, TypeError):
            tags = ()
        return Recommendation(
            recommendation_id=int(row["recommendation_id"]),
            pool=str(row["pool"]),
            path=str(row["path"]),
            content=str(row["content"]),
            weight=float(row["weight"]),
            tags=tags,
            creator_id=str(row["creator_id"]),
        )


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()
