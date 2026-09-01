from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from nonebot.log import logger

_LABELS = {
    "inbound": "IN",
    "outbound": "OUT",
    "notice": "EVENT",
    "ai_reply": "AI",
    "tool": "TOOL",
    "error": "ERROR",
}


class ActivityLogService:
    """Human-readable activity log paired with structured JSONL records."""

    def __init__(self, log_root: Path) -> None:
        self.directory = log_root / "activity"
        self._lock = asyncio.Lock()

    async def record(
        self,
        kind: str,
        summary: str,
        *,
        status: str = "success",
        user_id: str | None = None,
        group_id: str | None = None,
        message_id: str | None = None,
        details: dict[str, Any] | None = None,
        console: bool = True,
    ) -> None:
        now = datetime.now().astimezone()
        entry = {
            "timestamp": now.isoformat(timespec="seconds"),
            "kind": kind,
            "status": status,
            "user_id": user_id,
            "group_id": group_id,
            "message_id": message_id,
            "summary": _clean(summary, 4000),
            "details": _json_safe(details or {}),
        }
        json_path = self.directory / f"{now:%Y-%m-%d}.jsonl"
        text_path = self.directory / f"{now:%Y-%m-%d}.log"
        human = self._human_line(entry, now)
        async with self._lock:
            await asyncio.to_thread(self._append, json_path, text_path, entry, human)
        if console:
            level = "ERROR" if status == "failed" or kind == "error" else "INFO"
            logger.bind(amadeus_activity=True, activity_kind=kind).log(level, human.split(" | ", 1)[-1])

    def recent(
        self,
        limit: int = 30,
        *,
        user_id: str | None = None,
        group_id: str | None = None,
        kind: str | None = None,
    ) -> list[dict[str, Any]]:
        rows: deque[dict[str, Any]] = deque(maxlen=max(1, min(limit, 200)))
        if not self.directory.exists():
            return []
        for path in sorted(self.directory.glob("*.jsonl"), reverse=True)[:14]:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if user_id and str(row.get("user_id") or "") != str(user_id):
                    continue
                if group_id and str(row.get("group_id") or "") != str(group_id):
                    continue
                if kind and row.get("kind") != kind:
                    continue
                rows.appendleft(row)
                if len(rows) >= rows.maxlen:
                    return list(rows)
        return list(rows)

    @staticmethod
    def format_rows(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "没有匹配的活动日志。"
        lines = []
        for row in rows:
            timestamp = str(row.get("timestamp") or "").replace("T", " ")
            label = _LABELS.get(str(row.get("kind")), str(row.get("kind", "LOG")).upper())
            scope = (
                f"群 {row['group_id']}"
                if row.get("group_id")
                else f"私聊 {row['user_id']}"
                if row.get("user_id")
                else "系统"
            )
            lines.append(f"{timestamp} [{label}] {scope}\n{row.get('summary') or '-'}")
        return "\n\n".join(lines)

    @staticmethod
    def _append(
        json_path: Path,
        text_path: Path,
        entry: dict[str, Any],
        human: str,
    ) -> None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with json_path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        with text_path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(human + "\n")

    @staticmethod
    def _human_line(entry: dict[str, Any], now: datetime) -> str:
        label = _LABELS.get(str(entry["kind"]), str(entry["kind"]).upper())
        if entry.get("group_id"):
            scope = f"group={entry['group_id']} user={entry.get('user_id') or '-'}"
        elif entry.get("user_id"):
            scope = f"private user={entry['user_id']}"
        else:
            scope = "system"
        status = "" if entry["status"] == "success" else f" {entry['status']}"
        return f"{now:%H:%M:%S} {label}{status} {scope} | {entry['summary']}"


def summarize_message(message: Iterable[Any], *, reply_id: str | None = None) -> str:
    parts: list[str] = []
    if reply_id:
        parts.append(f"[回复 #{reply_id}]")
    for segment in message:
        kind = str(getattr(segment, "type", "unknown"))
        data = dict(getattr(segment, "data", {}) or {})
        if kind == "text":
            text = str(data.get("text") or "").strip()
            if text:
                parts.append(text)
        elif kind == "at":
            parts.append(f"[@{data.get('qq') or '?'}]")
        elif kind in {"image", "mface", "record", "video", "file"}:
            location = data.get("path") or data.get("url") or data.get("file") or data.get("id")
            parts.append(f"[{kind}: {_clean(str(location or '无地址'), 300)}]")
        elif kind == "face":
            parts.append(f"[表情 id={data.get('id') or '?'}]")
        elif kind == "reply":
            if not reply_id:
                parts.append(f"[回复 #{data.get('id') or '?'}]")
        else:
            preview = _clean(json.dumps(_json_safe(data), ensure_ascii=False), 300)
            parts.append(f"[{kind}: {preview}]")
    return _clean(" ".join(parts) or "[空消息]", 4000)


def sender_label(event: Any) -> str:
    user_id = str(getattr(event, "user_id", "") or "")
    sender = getattr(event, "sender", None)
    card = getattr(sender, "card", None) if sender is not None else None
    nickname = getattr(sender, "nickname", None) if sender is not None else None
    name = str(card or nickname or "").strip()
    return f"{name}({user_id})" if name else user_id or "未知用户"


def summarize_notice(event: Any) -> tuple[str, str, str | None, str | None, dict[str, Any]]:
    notice_type = str(getattr(event, "notice_type", "notice"))
    sub_type = str(getattr(event, "sub_type", "") or "")
    user_id = str(getattr(event, "user_id", "") or "") or None
    group_id = str(getattr(event, "group_id", "") or "") or None
    details = {
        key: getattr(event, key)
        for key in ("target_id", "operator_id", "message_id", "emoji_id", "file")
        if getattr(event, key, None) is not None
    }
    if notice_type == "notify" and sub_type == "poke":
        summary = f"{user_id or '?'} 戳了 {getattr(event, 'target_id', '?')}"
    elif notice_type == "group_msg_emoji_like":
        summary = (
            f"{user_id or '?'} 对消息 #{getattr(event, 'message_id', '?')} "
            f"回应表情 {getattr(event, 'emoji_id', '?')}"
        )
    else:
        summary = f"{notice_type}{'.' + sub_type if sub_type else ''}：{details or '无附加字段'}"
    return notice_type, summary, user_id, group_id, _json_safe(details)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return _clean(str(value), 1000)


def _clean(value: str, limit: int) -> str:
    text = value.replace("\r", " ").replace("\n", " ↵ ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"
