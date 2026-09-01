from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import UTC, datetime, timedelta

from nonebot import get_bots, get_driver
from nonebot.log import logger

from amadeus_bot.bootstrap import get_container
from amadeus_bot.services.campus import ActivitySource, PortalSource
from amadeus_bot.services.ddl import format_ddl
from amadeus_bot.services.jwgl import JwglSource

_task: asyncio.Task | None = None
_last_source_refresh = 0.0
_last_retention_cleanup = 0.0


@get_driver().on_startup
async def start_scheduler() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_scheduler_loop(), name="amadeus-scheduler")


@get_driver().on_shutdown
async def stop_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None


async def _scheduler_loop() -> None:
    while True:
        try:
            await dispatch_due_ddl_reminders()
            await dispatch_due_course_reminders()
            await refresh_campus_sources_if_due()
            await dispatch_daily_subscriptions()
            await cleanup_retained_files_if_due()
        except Exception:
            logger.exception("DDL 调度轮询失败")
        await asyncio.sleep(30)


async def dispatch_due_ddl_reminders() -> int:
    container = get_container()
    due = container.user_repository.due_reminders(datetime.now(UTC).isoformat())
    bots = list(get_bots().values())
    if not bots:
        return 0
    sent = 0
    bot = bots[0]
    for user_id, record in due:
        try:
            await bot.send_private_msg(user_id=int(user_id), message="DDL 提醒：\n" + format_ddl(record))
        except Exception:
            logger.exception("发送 DDL 提醒失败 user=%s ddl=%s", user_id, record.ddl_id)
            continue
        if container.user_repository.mark_reminder_sent(
            user_id, record.ddl_id, datetime.now(UTC).isoformat()
        ):
            sent += 1
    return sent


async def dispatch_due_course_reminders() -> int:
    container = get_container()
    bots = list(get_bots().values())
    if not bots:
        return 0
    sent = 0
    for user_id, course, occurrence in container.courses.due_reminders():
        try:
            await bots[0].send_private_msg(
                user_id=int(user_id),
                message=(
                    f"课程提醒：{course.name}\n第 {course.start_section}-{course.end_section} 节｜"
                    f"{course.location or '地点未填写'}｜{course.teacher or '教师未填写'}"
                ),
            )
        except Exception:
            logger.exception("发送课程提醒失败 user=%s course=%s", user_id, course.course_id)
            continue
        if container.courses.mark_reminder_sent(user_id, course.course_id, occurrence):
            sent += 1
    return sent


async def refresh_campus_sources_if_due() -> None:
    global _last_source_refresh
    now = time.monotonic()
    refresh_seconds = max(60, int(os.getenv("AMADEUS_CAMPUS_REFRESH_SECONDS", "300")))
    if now - _last_source_refresh < refresh_seconds:
        return
    _last_source_refresh = now
    container = get_container()
    sources = (
        ("portal", PortalSource(container.repository).refresh),
        ("activity", ActivitySource(container.repository).refresh),
        ("jwgl", JwglSource().keepalive),
    )
    for name, refresh in sources:
        previous = container.repository.get_source_health(name)
        try:
            await refresh()
            if name == "jwgl":
                container.repository.set_source_health(name, success=True)
            if previous and previous["consecutive_failures"]:
                await _notify_superusers(f"校园数据源 {name} 已恢复。")
        except Exception as exc:
            container.repository.set_source_health(name, success=False, error_summary=str(exc))
            if not previous or not previous["consecutive_failures"]:
                await _notify_superusers(f"校园数据源 {name} 会话失效或刷新失败：{exc}")


async def _notify_superusers(message: str) -> None:
    bots = list(get_bots().values())
    if not bots:
        return
    for user_id in get_container().permissions.superusers:
        try:
            await bots[0].send_private_msg(user_id=int(user_id), message=message)
        except Exception:
            logger.exception("发送校园数据源状态提醒失败 user=%s", user_id)


async def dispatch_daily_subscriptions() -> int:
    hour = int(os.getenv("AMADEUS_CAMPUS_PUSH_HOUR", "8"))
    now = datetime.now().astimezone()
    if now.hour != hour:
        return 0
    bots = list(get_bots().values())
    if not bots:
        return 0
    container = get_container()
    sent = 0
    for row in container.repository.list_subscriptions():
        if not row["enabled"]:
            continue
        key = f"campus:{row['source']}:{row['scope_type']}:{row['scope_id']}:{now.date()}"
        items = container.repository.query_source_items(str(row["source"]), limit=5)
        if not items or not container.repository.claim_delivery(key):
            continue
        text = f"{row['source']} 每日推送\n\n" + "\n\n".join(
            f"{item['title']}\n{item.get('published_at') or ''}\n{item.get('url') or ''}" for item in items
        )
        try:
            if row["scope_type"] == "group":
                await bots[0].send_group_msg(group_id=int(row["scope_id"]), message=text)
            else:
                await bots[0].send_private_msg(user_id=int(row["scope_id"]), message=text)
            sent += 1
        except Exception:
            logger.exception("校园每日推送失败 source=%s scope=%s", row["source"], row["scope_id"])
    return sent


async def cleanup_retained_files_if_due() -> int:
    global _last_retention_cleanup
    now_monotonic = time.monotonic()
    if now_monotonic - _last_retention_cleanup < 86400:
        return 0
    _last_retention_cleanup = now_monotonic
    container = get_container()
    config = container.paths.data / "shared" / "retention.json"
    if not config.is_file():
        return 0
    try:
        days = int(json.loads(config.read_text(encoding="utf-8"))["days"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 0
    cutoff = datetime.now().timestamp() - timedelta(days=days).total_seconds()
    roots = (container.paths.logs, container.paths.data / "cache" / "render")
    removed = 0
    for root in roots:
        if not root.exists():
            continue
        root_resolved = root.resolve()
        for path in root.rglob("*"):
            if not path.is_file() or path.stat().st_mtime >= cutoff:
                continue
            resolved = path.resolve()
            if root_resolved not in resolved.parents:
                continue
            path.unlink(missing_ok=True)
            removed += 1
    return removed
