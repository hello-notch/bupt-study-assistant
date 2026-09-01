import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from amadeus_bot.services.activity_log import (
    ActivityLogService,
    summarize_message,
    summarize_notice,
)


@dataclass
class FakeSegment:
    type: str
    data: dict


@pytest.mark.asyncio
async def test_activity_log_writes_human_and_structured_files(tmp_path: Path) -> None:
    service = ActivityLogService(tmp_path)
    await service.record(
        "inbound",
        "测试用户(100)：你好",
        user_id="100",
        group_id="200",
        message_id="300",
        details={"event": "message.group.normal"},
        console=False,
    )

    json_files = list((tmp_path / "activity").glob("*.jsonl"))
    text_files = list((tmp_path / "activity").glob("*.log"))
    assert len(json_files) == len(text_files) == 1
    row = json.loads(json_files[0].read_text(encoding="utf-8").strip())
    assert row["kind"] == "inbound"
    assert row["group_id"] == "200"
    assert "你好" in text_files[0].read_text(encoding="utf-8")
    assert service.recent(group_id="200")[0]["message_id"] == "300"
    assert service.recent(user_id="other") == []


def test_message_summary_includes_reply_at_and_media_location() -> None:
    summary = summarize_message(
        [
            FakeSegment("text", {"text": "看看"}),
            FakeSegment("at", {"qq": "42"}),
            FakeSegment("image", {"url": "https://example.invalid/a.png"}),
            FakeSegment("face", {"id": "66"}),
        ],
        reply_id="123",
    )
    assert "回复 #123" in summary
    assert "@42" in summary
    assert "https://example.invalid/a.png" in summary
    assert "表情 id=66" in summary


def test_notice_summary_includes_poke_and_message_reaction() -> None:
    poke = type(
        "Poke",
        (),
        {"notice_type": "notify", "sub_type": "poke", "user_id": 1, "target_id": 2},
    )()
    reaction = type(
        "Reaction",
        (),
        {
            "notice_type": "group_msg_emoji_like",
            "sub_type": "",
            "user_id": 1,
            "group_id": 2,
            "message_id": 3,
            "emoji_id": 66,
        },
    )()
    assert summarize_notice(poke)[1] == "1 戳了 2"
    assert "消息 #3" in summarize_notice(reaction)[1]
    assert "表情 66" in summarize_notice(reaction)[1]
