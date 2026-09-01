from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class IssueReportService:
    """Create a bounded, local diagnostic bundle around one message."""

    def __init__(self, project_root: Path, log_root: Path) -> None:
        self.issue_root = project_root / "issues"
        self.log_root = log_root

    async def capture(
        self,
        *,
        anchor_timestamp: int,
        anchor_message_id: str,
        group_id: str | None,
        user_id: str,
        command_message: dict[str, Any],
        replied_message: dict[str, Any] | None,
        note: str = "",
    ) -> Path:
        return await asyncio.to_thread(
            self._capture,
            anchor_timestamp=anchor_timestamp,
            anchor_message_id=anchor_message_id,
            group_id=group_id,
            user_id=user_id,
            command_message=command_message,
            replied_message=replied_message,
            note=note,
        )

    def _capture(self, **values: Any) -> Path:
        anchor = datetime.fromtimestamp(int(values["anchor_timestamp"])).astimezone()
        safe_id = re.sub(r"[^0-9A-Za-z_-]", "_", str(values["anchor_message_id"]))[:40] or "nearby"
        directory = self.issue_root / f"{anchor:%Y%m%d-%H%M%S}-{safe_id}"
        suffix = 2
        while directory.exists():
            directory = self.issue_root / f"{anchor:%Y%m%d-%H%M%S}-{safe_id}-{suffix}"
            suffix += 1
        directory.mkdir(parents=True)

        metadata = {
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "anchor_at": anchor.isoformat(timespec="seconds"),
            "anchor_message_id": values["anchor_message_id"],
            "scope": "group" if values["group_id"] else "private",
            "group_id": values["group_id"],
            "user_id": values["user_id"],
            "mode": "reply" if values["replied_message"] else "nearby",
            "note": values["note"],
        }
        messages = self._message_context(anchor, group_id=values["group_id"], user_id=values["user_id"])
        activity = self._activity_context(anchor, group_id=values["group_id"], user_id=values["user_id"])
        runtime = self._runtime_context(anchor)

        self._write_json(directory / "metadata.json", metadata)
        self._write_json(directory / "command_message.json", values["command_message"])
        if values["replied_message"] is not None:
            self._write_json(directory / "replied_message.json", values["replied_message"])
        self._write_jsonl(directory / "messages.jsonl", messages)
        self._write_jsonl(directory / "activity.jsonl", activity)
        (directory / "runtime.log").write_text("\n".join(runtime), encoding="utf-8")
        (directory / "README.md").write_text(
            "# 机器人问题快照\n\n"
            f"- 锚点时间：{metadata['anchor_at']}\n"
            f"- 锚点消息：{metadata['anchor_message_id']}\n"
            f"- 采集方式：{'回复指定消息' if values['replied_message'] else '命令附近'}\n"
            f"- 消息上下文：{len(messages)} 条\n"
            f"- 活动日志：{len(activity)} 条\n"
            f"- 运行日志：{len(runtime)} 行\n"
            f"- 说明：{values['note'] or '未填写'}\n",
            encoding="utf-8",
        )
        return directory

    def _message_context(
        self, anchor: datetime, *, group_id: str | None, user_id: str
    ) -> list[dict[str, Any]]:
        if group_id:
            directory = self.log_root / "messages" / group_id
        else:
            directory = self.log_root / "private" / user_id
        rows = self._read_jsonl_dates(directory, anchor, days=1)
        rows.sort(key=lambda row: int(row.get("timestamp") or 0))
        nearby = [
            row for row in rows if abs(int(row.get("timestamp") or 0) - int(anchor.timestamp())) <= 5 * 60
        ]
        if nearby:
            return nearby[:40]
        return sorted(
            rows,
            key=lambda row: abs(int(row.get("timestamp") or 0) - int(anchor.timestamp())),
        )[:11]

    def _activity_context(
        self, anchor: datetime, *, group_id: str | None, user_id: str
    ) -> list[dict[str, Any]]:
        rows = self._read_jsonl_dates(self.log_root / "activity", anchor, days=1)
        result = []
        for row in rows:
            try:
                timestamp = datetime.fromisoformat(str(row.get("timestamp")))
            except (TypeError, ValueError):
                continue
            if abs((timestamp.astimezone() - anchor).total_seconds()) > 5 * 60:
                continue
            if group_id and str(row.get("group_id") or "") != group_id:
                continue
            if not group_id and str(row.get("user_id") or "") != user_id:
                continue
            result.append(row)
        return result[:100]

    def _runtime_context(self, anchor: datetime) -> list[str]:
        path = self.log_root / "runtime" / "runtime.log"
        if not path.is_file():
            return []
        result = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
            if not match:
                continue
            timestamp = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S").astimezone()
            if abs((timestamp - anchor).total_seconds()) <= 5 * 60:
                result.append(line)
        return result[:300]

    @staticmethod
    def _read_jsonl_dates(directory: Path, anchor: datetime, *, days: int) -> list[dict[str, Any]]:
        result = []
        for offset in range(-days, days + 1):
            path = directory / f"{(anchor + timedelta(days=offset)):%Y-%m-%d}.jsonl"
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    result.append(value)
        return result

    @staticmethod
    def _write_json(path: Path, value: Any) -> None:
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
        text = "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows)
        path.write_text(text, encoding="utf-8")
