from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from amadeus_bot.repositories.user_data import DDLRecord, UserDataRepository

SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True, slots=True)
class DDLCreateResult:
    record: DDLRecord
    reminder_reason: str


class DDLService:
    def __init__(self, repository: UserDataRepository) -> None:
        self.repository = repository

    def add(
        self,
        user_id: str,
        deadline_text: str,
        content: str,
        *,
        reminder: str | None = None,
        now: datetime | None = None,
    ) -> DDLCreateResult:
        current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
        deadline = parse_deadline(deadline_text, now=current)
        content = content.strip()
        if not content:
            raise ValueError("DDL 内容不能为空")
        if deadline <= current:
            raise ValueError("截止时间必须晚于当前时间")
        reminder_at: datetime | None
        reminder_mode = reminder.strip().lower() if reminder else ""
        if reminder_mode == "off":
            reminder_at = None
            reminder_reason = "已按要求关闭提醒"
        elif reminder_mode in {"at", "准时", "到时"}:
            reminder_at = deadline
            reminder_reason = "在截止时间准时提醒"
        elif reminder_mode:
            advance = parse_duration(reminder_mode)
            reminder_at = deadline - advance
            if reminder_at <= current:
                raise ValueError("自定义提醒时间必须晚于当前时间")
            reminder_reason = f"自定义提前 {format_duration(advance)} 提醒"
        elif deadline - current < timedelta(hours=1):
            reminder_at = None
            reminder_reason = "创建时距截止不足 1 小时，不设置默认提醒"
        else:
            reminder_at = deadline - timedelta(hours=1)
            reminder_reason = "默认提前 1 小时提醒"
        current_utc = current.astimezone(UTC)
        record = self.repository.add_ddl(
            str(user_id),
            content,
            deadline.astimezone(UTC).isoformat(),
            reminder_at.astimezone(UTC).isoformat() if reminder_at else None,
            current_utc.isoformat(),
        )
        return DDLCreateResult(record, reminder_reason)

    def list(self, user_id: str, status: str = "todo") -> list[DDLRecord]:
        return self.repository.list_ddl(str(user_id), status)

    def done(self, user_id: str, ddl_id: int) -> bool:
        return self.repository.mark_done(str(user_id), ddl_id, datetime.now(UTC).isoformat())

    def delete(self, user_id: str, ddl_id: int) -> bool:
        return self.repository.soft_delete(str(user_id), ddl_id, datetime.now(UTC).isoformat())

    def set_reminder(self, user_id: str, ddl_id: int, reminder: str) -> bool:
        record = self.repository.get_ddl(str(user_id), ddl_id)
        if record is None:
            return False
        deadline = datetime.fromisoformat(record.deadline_utc)
        now = datetime.now(UTC)
        reminder_mode = reminder.strip().lower()
        if reminder_mode == "off":
            reminder_at = None
        elif reminder_mode in {"at", "准时", "到时"}:
            reminder_at = deadline
        else:
            reminder_at = deadline - parse_duration(reminder_mode)
        if reminder_at is not None and reminder_at <= now:
            raise ValueError("提醒时间必须晚于当前时间")
        return self.repository.set_reminder(
            str(user_id), ddl_id, reminder_at.isoformat() if reminder_at else None, now.isoformat()
        )

    def edit(
        self,
        user_id: str,
        ddl_id: int,
        *,
        deadline_text: str | None = None,
        content: str | None = None,
        now: datetime | None = None,
    ) -> DDLRecord | None:
        current = self.repository.get_ddl(str(user_id), ddl_id)
        if current is None or current.status != "todo":
            return None
        current_time = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
        deadline_utc: str | None = None
        reminder_at_utc: str | None = None
        if deadline_text is not None:
            deadline = parse_deadline(deadline_text, now=current_time)
            if deadline <= current_time:
                raise ValueError("截止时间必须晚于当前时间")
            deadline_utc = deadline.astimezone(UTC).isoformat()
            if deadline - current_time >= timedelta(hours=1):
                reminder_at_utc = (deadline - timedelta(hours=1)).astimezone(UTC).isoformat()
        if content is not None and not content.strip():
            raise ValueError("DDL 内容不能为空")
        changed = self.repository.edit_ddl(
            str(user_id),
            ddl_id,
            content=content.strip() if content is not None else None,
            deadline_utc=deadline_utc,
            reminder_at_utc=reminder_at_utc,
            updated_at_utc=current_time.astimezone(UTC).isoformat(),
        )
        return self.repository.get_ddl(str(user_id), ddl_id) if changed else None


def parse_deadline(value: str, *, now: datetime | None = None) -> datetime:
    text = value.strip().replace("：", ":")
    current = (now or datetime.now(SHANGHAI)).astimezone(SHANGHAI)
    after = re.fullmatch(
        r"(\d+|[零〇一二两三四五六七八九十百]+)\s*(分钟|分|小时|钟头|天)后",
        text,
    )
    if after:
        amount = _parse_positive_integer(after.group(1))
        unit = after.group(2)
        if unit in {"分钟", "分"}:
            return current + timedelta(minutes=amount)
        if unit in {"小时", "钟头"}:
            return current + timedelta(hours=amount)
        return current + timedelta(days=amount)
    relative = re.fullmatch(
        r"(今天|明天|后天)\s*(上午|中午|下午|晚上)?\s*([0-2]?\d|[零一二三四五六七八九十两]+)"
        r"(?:(?::|点|时)([0-5]?\d|半)?)?(?:分)?",
        text,
    )
    if relative:
        day_offset = {"今天": 0, "明天": 1, "后天": 2}[relative.group(1)]
        period = relative.group(2) or ""
        hour = _parse_hour(relative.group(3))
        minute_text = relative.group(4)
        minute = 30 if minute_text == "半" else int(minute_text or 0)
        if period in {"下午", "晚上"} and hour < 12:
            hour += 12
        if period == "中午" and hour < 11:
            hour += 12
        return (current + timedelta(days=day_offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
    clock = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", text)
    if clock:
        target = current.replace(
            hour=int(clock.group(1)), minute=int(clock.group(2)), second=0, microsecond=0
        )
        return target if target > current else target + timedelta(days=1)
    normalized = text.replace("年", "-").replace("月", "-").replace("日", " ").strip()
    for candidate in (normalized, normalized.replace(" ", "T", 1)):
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SHANGHAI)
        return parsed.astimezone(SHANGHAI)
    raise ValueError("无法识别截止时间；示例：2分钟后、明天下午三点、23:59、2026-08-29 15:00")


def parse_duration(value: str) -> timedelta:
    text = value.strip().lower()
    match = re.fullmatch(r"(\d+)\s*(m|min|分钟|h|hour|小时|d|day|天)", text)
    if not match:
        raise ValueError("提前量格式示例：30m、1小时、2天或 off")
    amount = int(match.group(1))
    if amount <= 0:
        raise ValueError("提前量必须大于 0")
    unit = match.group(2)
    if unit in {"m", "min", "分钟"}:
        return timedelta(minutes=amount)
    if unit in {"h", "hour", "小时"}:
        return timedelta(hours=amount)
    return timedelta(days=amount)


def format_ddl(record: DDLRecord) -> str:
    deadline = datetime.fromisoformat(record.deadline_utc).astimezone(SHANGHAI)
    reminder = (
        datetime.fromisoformat(record.reminder_at_utc).astimezone(SHANGHAI).strftime("%m-%d %H:%M")
        if record.reminder_at_utc
        else "无"
    )
    return (
        f"#{record.ddl_id} [{record.status}] {record.content}\n"
        f"  截止：{deadline:%Y-%m-%d %H:%M}｜提醒：{reminder}"
    )


def format_duration(value: timedelta) -> str:
    seconds = int(value.total_seconds())
    if seconds % 86400 == 0:
        return f"{seconds // 86400} 天"
    if seconds % 3600 == 0:
        return f"{seconds // 3600} 小时"
    return f"{seconds // 60} 分钟"


def _parse_hour(value: str) -> int:
    if value.isdigit():
        hour = int(value)
    else:
        numerals = {
            "零": 0,
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }
        if value == "十":
            hour = 10
        elif value.startswith("十"):
            hour = 10 + numerals[value[1:]]
        elif value.endswith("十"):
            hour = numerals[value[0]] * 10
        elif "十" in value:
            left, right = value.split("十", 1)
            hour = numerals[left] * 10 + numerals[right]
        else:
            hour = numerals[value]
    if not 0 <= hour <= 23:
        raise ValueError("小时必须在 0～23 之间")
    return hour


def _parse_positive_integer(value: str) -> int:
    if value.isdigit():
        amount = int(value)
    else:
        digits = {
            "零": 0,
            "〇": 0,
            "一": 1,
            "二": 2,
            "两": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
            "七": 7,
            "八": 8,
            "九": 9,
        }
        if "百" in value:
            left, right = value.split("百", 1)
            amount = digits.get(left, 1) * 100
            value = right
        else:
            amount = 0
        if value:
            if "十" in value:
                left, right = value.split("十", 1)
                amount += digits.get(left, 1) * 10 + (digits[right] if right else 0)
            else:
                amount += digits[value]
    if amount <= 0:
        raise ValueError("相对时间必须大于 0")
    return amount
