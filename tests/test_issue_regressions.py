import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from amadeus_bot.repositories.user_data import UserDataRepository
from amadeus_bot.services.courses import CourseService, parse_bupt_timetable_rows
from amadeus_bot.services.ddl import DDLService, parse_deadline
from amadeus_bot.services.event_utils import onebot_message
from amadeus_bot.services.feature_flags import DEFAULT_FEATURES
from amadeus_bot.services.issue_report import IssueReportService
from amadeus_bot.services.jwgl import parse_class_lookup, parse_class_schedule

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_single_segment_get_msg_payload_is_accepted() -> None:
    message = onebot_message(
        {"type": "file", "data": {"file": "学生个人课表.xls", "url": "https://example.test/a"}}
    )
    assert len(message) == 1
    assert message[0].type == "file"


def test_activity_feature_is_enabled_by_default() -> None:
    assert DEFAULT_FEATURES["activity"] is True


def test_bupt_timetable_matrix_parser_and_preview(tmp_path: Path) -> None:
    values = [
        ["北京邮电大学 学生个人课表", "", "", "", "", "", "", ""],
        ["", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"],
        [
            "1\n08:00-08:45",
            "\n高等数学\n张老师\n1-16[周]\n教一-101\n[01-02]节",
            " ",
            " ",
            " ",
            " ",
            " ",
            " ",
        ],
    ]
    rows = parse_bupt_timetable_rows(values)
    assert rows == [
        {
            "name": "高等数学",
            "teacher": "张老师",
            "location": "教一-101",
            "weekday": 1,
            "start_section": 1,
            "end_section": 2,
            "weeks": "1-16",
        }
    ]
    service = CourseService(UserDataRepository(tmp_path / "users"))
    preview = service.preview_rows("100", rows, "jwgl.xls")
    assert preview.rows[0]["name"] == "高等数学"


def test_jwgl_current_lookup_shape_and_schedule_grid() -> None:
    assert parse_class_lookup('{"list":[{"bj":"2024218601","xx04id":"internal-id"}]}', "2024218601") == (
        "internal-id",
        "2024218601",
    )

    course = (
        '<div class="kbcontent1">高等数学2024218601<br>张老师\n(3-18周)<br>教一-101<br>线下面授讲课</div>'
    )
    cells = [course, course] + ["&nbsp;"] * 96
    html = "<tr><td>2024218601</td>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>"
    rows = parse_class_schedule(html, "2024218601")
    assert rows[0] == {
        "name": "高等数学",
        "teacher": "张老师",
        "location": "教一-101",
        "weekday": 1,
        "start_section": 1,
        "end_section": 2,
        "weeks": "3-18",
        "campus": "",
    }


def test_relative_deadline_clock_and_on_time_reminder(tmp_path: Path) -> None:
    now = datetime(2026, 8, 31, 23, 59, tzinfo=SHANGHAI)
    assert parse_deadline("2分钟后", now=now) == datetime(2026, 9, 1, 0, 1, tzinfo=SHANGHAI)
    assert parse_deadline("两分钟后", now=now) == datetime(2026, 9, 1, 0, 1, tzinfo=SHANGHAI)
    assert parse_deadline("23:58", now=now) == datetime(2026, 9, 1, 23, 58, tzinfo=SHANGHAI)

    service = DDLService(UserDataRepository(tmp_path / "users"))
    created = service.add("100", "2分钟后", "测试提醒", reminder="at", now=now)
    assert created.record.reminder_at_utc == created.record.deadline_utc
    assert "准时" in created.reminder_reason


@pytest.mark.asyncio
async def test_issue_report_captures_bounded_context(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    anchor = datetime(2026, 8, 31, 23, 59, tzinfo=SHANGHAI)
    message_dir = logs / "messages" / "930"
    activity_dir = logs / "activity"
    runtime_dir = logs / "runtime"
    message_dir.mkdir(parents=True)
    activity_dir.mkdir(parents=True)
    runtime_dir.mkdir(parents=True)
    message = {"message_id": "10", "timestamp": int(anchor.timestamp()), "plain_text": "异常"}
    (message_dir / "2026-08-31.jsonl").write_text(
        json.dumps(message, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    activity = {
        "timestamp": anchor.isoformat(timespec="seconds"),
        "kind": "error",
        "group_id": "930",
        "user_id": "100",
        "summary": "测试错误",
    }
    (activity_dir / "2026-08-31.jsonl").write_text(
        json.dumps(activity, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (runtime_dir / "runtime.log").write_text(
        "2026-08-31 23:59:00 | ERROR | test | 测试错误\n", encoding="utf-8"
    )

    directory = await IssueReportService(tmp_path, logs).capture(
        anchor_timestamp=int(anchor.timestamp()),
        anchor_message_id="10",
        group_id="930",
        user_id="100",
        command_message={"message_id": "11"},
        replied_message={"message_id": "10"},
        note="测试",
    )
    assert json.loads((directory / "metadata.json").read_text(encoding="utf-8"))["mode"] == "reply"
    assert "异常" in (directory / "messages.jsonl").read_text(encoding="utf-8")
    assert "测试错误" in (directory / "activity.jsonl").read_text(encoding="utf-8")
    assert "ERROR" in (directory / "runtime.log").read_text(encoding="utf-8")
