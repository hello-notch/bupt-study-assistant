from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AnalyticsWindow:
    group_id: str
    hours: int
    start: datetime
    end: datetime
    records: tuple[dict[str, Any], ...]

    @property
    def effective_records(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            row
            for row in self.records
            if str(row.get("plain_text", "")).strip()
            and not str(row.get("plain_text", "")).lstrip().startswith("/")
        )


class AnalyticsService:
    def __init__(self, log_root: Path) -> None:
        self.log_root = log_root

    def load_group(self, group_id: str, hours: int, *, now: datetime | None = None) -> AnalyticsWindow:
        if not 1 <= hours <= 24:
            raise ValueError("N 必须是 1～24 的整数")
        end = now or datetime.now().astimezone()
        start = end - timedelta(hours=hours)
        directory = self.log_root / "messages" / str(group_id)
        records: list[dict[str, Any]] = []
        for day in {start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")}:
            path = directory / f"{day}.jsonl"
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                    timestamp = int(row.get("timestamp", 0))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                moment = datetime.fromtimestamp(timestamp).astimezone()
                if start <= moment <= end:
                    records.append(row)
        records.sort(key=lambda item: int(item.get("timestamp", 0)))
        return AnalyticsWindow(str(group_id), hours, start, end, tuple(records))

    @staticmethod
    def deterministic(window: AnalyticsWindow, user_id: str | None = None) -> dict[str, Any]:
        rows = [row for row in window.records if user_id is None or str(row.get("user_id")) == user_id]
        segment_counts: Counter[str] = Counter()
        text_chars = 0
        links = 0
        replies = 0
        hours: Counter[int] = Counter()
        users: Counter[str] = Counter()
        for row in rows:
            text = str(row.get("plain_text", ""))
            if not text.lstrip().startswith("/"):
                text_chars += len(re.sub(r"\s+", "", text))
            links += len(re.findall(r"https?://\S+", text))
            moment = datetime.fromtimestamp(int(row.get("timestamp", 0))).astimezone()
            hours[moment.hour] += 1
            users[str(row.get("user_id", ""))] += 1
            for segment in row.get("segments", []):
                kind = str(segment.get("type", "unknown"))
                segment_counts[kind] += 1
                if kind == "reply":
                    replies += 1
        return {
            "messages": len(rows),
            "text_chars": text_chars,
            "links": links,
            "replies": replies,
            "active_users": len(users),
            "users": users,
            "segments": segment_counts,
            "hours": hours,
        }

    @staticmethod
    def ai_transcript(window: AnalyticsWindow, *, max_chars: int = 18_000) -> str:
        lines = []
        size = 0
        for row in window.effective_records:
            text = str(row.get("plain_text", "")).strip()
            if not text:
                text = (
                    "[非文本消息："
                    + ",".join(str(segment.get("type", "unknown")) for segment in row.get("segments", []))
                    + "]"
                )
            line = f"{row.get('user_id')}: {text[:500]}"
            if size + len(line) > max_chars:
                break
            lines.append(line)
            size += len(line)
        return "\n".join(lines)


def format_deterministic(window: AnalyticsWindow, stats: dict[str, Any]) -> str:
    segments: Counter[str] = stats["segments"]
    return (
        f"时间：{window.start:%Y-%m-%d %H:%M} ～ {window.end:%Y-%m-%d %H:%M}\n"
        f"消息：{stats['messages']}｜纯文本字数：{stats['text_chars']}｜活跃用户：{stats['active_users']}\n"
        f"图片：{segments['image']}｜表情包：{segments['mface']}｜QQ 表情：{segments['face']}｜"
        f"语音：{segments['record']}｜回复：{stats['replies']}｜链接：{stats['links']}"
    )
