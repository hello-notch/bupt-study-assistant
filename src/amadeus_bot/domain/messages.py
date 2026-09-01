from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SegmentRecord:
    type: str
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MessageRecord:
    message_id: str
    direction: str
    scene: str
    user_id: str
    group_id: str | None
    self_id: str
    plain_text: str
    timestamp: int
    segments: tuple[SegmentRecord, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
