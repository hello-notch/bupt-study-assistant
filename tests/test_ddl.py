from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from amadeus_bot.repositories.user_data import UserDataRepository
from amadeus_bot.services.ddl import DDLService, parse_deadline, parse_duration

SHANGHAI = ZoneInfo("Asia/Shanghai")


def make_service(path: Path) -> DDLService:
    return DDLService(UserDataRepository(path / "users"))


def test_parse_chinese_deadline() -> None:
    now = datetime(2026, 8, 28, 14, 0, tzinfo=SHANGHAI)
    assert parse_deadline("明天下午三点", now=now) == datetime(2026, 8, 29, 15, 0, tzinfo=SHANGHAI)
    assert parse_deadline("明天15:30", now=now) == datetime(2026, 8, 29, 15, 30, tzinfo=SHANGHAI)
    assert parse_duration("1小时").total_seconds() == 3600


def test_default_reminder_and_short_deadline_rule(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    now = datetime(2026, 8, 28, 14, 0, tzinfo=SHANGHAI)

    normal = service.add("100", "明天下午三点", "数学作业", now=now)
    assert normal.record.reminder_at_utc is not None
    assert normal.reminder_reason == "默认提前 1 小时提醒"

    short = service.add("100", "今天14:30", "半小时后的事", now=now)
    assert short.record.reminder_at_utc is None
    assert "不足 1 小时" in short.reminder_reason


def test_explicit_reminder_override_and_user_isolation(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    now = datetime(2026, 8, 28, 14, 0, tzinfo=SHANGHAI)

    created = service.add("100", "明天15:00", "作业", reminder="off", now=now)
    assert created.record.reminder_at_utc is None
    assert len(service.list("100")) == 1
    assert service.list("200") == []


def test_rejects_path_traversal_user_id(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    now = datetime(2026, 8, 28, 14, 0, tzinfo=SHANGHAI)
    with pytest.raises(ValueError, match="QQ"):
        service.add("../100", "明天15:00", "作业", now=now)
