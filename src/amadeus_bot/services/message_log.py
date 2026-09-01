from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from amadeus_bot.domain.messages import MessageRecord, SegmentRecord
from amadeus_bot.services.event_utils import event_group_id


class MessageNormalizer:
    @staticmethod
    def from_onebot_event(event: Any, *, direction: str = "inbound") -> MessageRecord:
        group_id = event_group_id(event)
        segments = tuple(
            SegmentRecord(type=str(segment.type), data=dict(segment.data)) for segment in event.get_message()
        )
        return MessageRecord(
            message_id=str(getattr(event, "message_id", "")),
            direction=direction,
            scene="group" if group_id is not None else "private",
            user_id=str(event.get_user_id()),
            group_id=group_id,
            self_id=str(getattr(event, "self_id", "")),
            plain_text=event.get_plaintext(),
            timestamp=int(getattr(event, "time", 0)),
            segments=segments,
        )


class MessageLogService:
    def __init__(self, log_root: Path) -> None:
        self.log_root = log_root
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def append(self, record: MessageRecord) -> Path:
        date = datetime.fromtimestamp(record.timestamp).strftime("%Y-%m-%d")
        if record.group_id:
            path = self.log_root / "messages" / record.group_id / f"{date}.jsonl"
        else:
            path = self.log_root / "private" / record.user_id / f"{date}.jsonl"
        payload = json.dumps(record.as_dict(), ensure_ascii=False, separators=(",", ":")) + "\n"
        async with self._locks[str(path)]:
            await asyncio.to_thread(self._append_text, path, payload)
        return path

    @staticmethod
    def _append_text(path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="") as stream:
            stream.write(payload)
