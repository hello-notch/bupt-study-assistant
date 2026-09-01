from __future__ import annotations

import secrets
import shlex
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import (
    event_group_id,
    finish_text_or_image,
    onebot_message,
    reply_message_id,
)
from amadeus_bot.services.courses import parse_sections, parse_weekday
from amadeus_bot.services.jwgl import JwglSource

command_registry.register(
    CommandSpec(
        name="course",
        description="导入、查询、编辑课程表并设置私聊提醒",
        usage=(
            "/course import-class <班级号> [学年学期]；回复表格 /course import-file；"
            "/course import-confirm <token>；/course list [周次]；/course today|tomorrow；"
            "/course add <课程名> <星期> <节次> <周次> [地点] [教师]；"
            "/course edit <id> --name/--weekday/--sections/--weeks/--location/--teacher <值>；"
            "/course delete <id> [token]；/course remind <id/all> <提前分钟/off>"
        ),
        permission=PermissionLevel.SELF_OR_SUPERUSER,
        feature="course",
        ai_callable=True,
        examples=(
            "/course import-class 2023211301",
            "/course today",
            "/course add 高等数学 一 1-2 1-16 教三-101 张老师",
            "/course remind all 20",
        ),
        notes=(
            "import-file 必须回复不超过 10 MiB 的 CSV/XLS/XLSX 文件，并再次 import-confirm",
            "XLS/XLSX 必须使用教务系统直接下载的个人课表，自行制作或另存的表格可能无法识别",
            "delete 需要在 2 分钟内使用确认 token",
            "默认只操作本人；仅 SUPERUSER 可用 --user <QQ> 指定其他用户",
            "课程提醒通过私聊发送，依赖 .env 中的学期开始日期和节次时间",
        ),
    )
)

course_command = on_command("course", priority=10, block=True)
_delete_tokens: dict[str, tuple[str, int, float]] = {}


@course_command.handle()
async def handle_course(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    group_id = event_group_id(event)
    if group_id and not get_container().features.status("course", group_id).enabled:
        await course_command.finish("当前群已关闭课程表功能。")
    try:
        tokens = shlex.split(arguments.extract_plain_text())
        subject, tokens = _extract_subject(event.get_user_id(), tokens)
        if not tokens:
            raise ValueError("请提供课程表子命令")
        action = tokens.pop(0).lower()
        if action == "import-file":
            text = await _import_file(bot, event, subject)
        elif action == "import-class":
            text = await _import_class(subject, tokens)
        else:
            text = _execute(subject, action, tokens)
    except ValueError as exc:
        await course_command.finish(f"参数错误：{exc}")
    except RuntimeError as exc:
        await course_command.finish(f"数据源错误：{exc}")
    await finish_text_or_image(course_command, text, title="课程表", force_image=len(text) > 500)


async def _import_class(user_id: str, tokens: list[str]) -> str:
    if not tokens:
        raise ValueError("用法：/course import-class <班级号> [学年学期]")
    display, rows = await JwglSource().query_class(tokens[0], tokens[1] if len(tokens) > 1 else "")
    preview = get_container().courses.preview_rows(user_id, rows, f"jwgl:{display}")
    return (
        f"已匹配班级：{display}\n解析课程：{len(rows)} 门\n确认导入：/course import-confirm {preview.token}"
    )


async def _import_file(bot: Bot, event, user_id: str) -> str:
    reply_id = reply_message_id(event)
    if not reply_id:
        raise ValueError("请回复教务系统下载的 .xls/.xlsx 课表或 .csv 文件后使用 /course import-file")
    detail = await bot.get_msg(message_id=int(reply_id))
    message = onebot_message(detail.get("message"))
    segment = next((item for item in message if item.type == "file"), None)
    if segment is None or not segment.data.get("url"):
        raise ValueError("被回复消息中没有可下载文件")
    filename = str(segment.data.get("name") or segment.data.get("file") or "course.csv")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(str(segment.data["url"]))
        response.raise_for_status()
    if len(response.content) > 10 * 1024 * 1024:
        raise ValueError("文件不能超过 10 MiB")
    suffix = Path(filename).suffix.lower()
    if suffix == ".csv":
        preview = get_container().courses.preview_csv(user_id, response.content, filename)
    elif suffix in {".xls", ".xlsx"}:
        with tempfile.TemporaryDirectory(prefix="amadeus-course-") as directory:
            path = Path(directory) / f"course{suffix}"
            path.write_bytes(response.content)
            preview = (
                get_container().courses.preview_xls(user_id, path)
                if suffix == ".xls"
                else get_container().courses.preview_xlsx(user_id, path)
            )
    else:
        raise ValueError("只支持教务系统下载的 .xls/.xlsx 课表或 .csv")
    return f"列映射成功，识别 {len(preview.rows)} 行。确认导入：/course import-confirm {preview.token}"


def _execute(user_id: str, action: str, tokens: list[str]) -> str:
    service = get_container().courses
    if action == "import-confirm":
        if len(tokens) != 1:
            raise ValueError("用法：/course import-confirm <token>")
        batch_id, count = service.confirm(user_id, tokens[0])
        return f"导入完成：批次 {batch_id}，写入 {count} 门课程。"
    if action in {"list", "today", "tomorrow"}:
        weekday = None
        if action in {"today", "tomorrow"}:
            day = datetime.now().astimezone() + (timedelta(days=1) if action == "tomorrow" else timedelta())
            weekday = day.isoweekday()
        week = int(tokens[0]) if action == "list" and tokens and tokens[0].isdigit() else None
        rows = service.list(user_id, weekday)
        if week is not None:
            from amadeus_bot.services.courses import normalize_weeks

            rows = [row for row in rows if week in normalize_weeks(row.weeks)]
        return "\n".join(_format_course(row) for row in rows) or "没有课程。"
    if action == "add":
        if len(tokens) < 4:
            raise ValueError("用法：/course add <课程名> <星期> <节次> <周次> [地点] [教师]")
        course_id = service.add(
            user_id,
            tokens[0],
            parse_weekday(tokens[1]),
            parse_sections(tokens[2]),
            tokens[3],
            tokens[4] if len(tokens) > 4 else "",
            tokens[5] if len(tokens) > 5 else "",
        )
        return f"已添加课程 #{course_id}。"
    if action == "edit":
        if not tokens or not tokens[0].isdigit():
            raise ValueError(
                "用法：/course edit <id> --name/--weekday/--sections/--weeks/--location/--teacher ..."
            )
        course_id = int(tokens.pop(0))
        changes = _course_changes(tokens)
        return "已修改课程。" if service.edit(user_id, course_id, changes) else "课程不存在。"
    if action == "remind":
        if len(tokens) != 2 or (tokens[0] != "all" and not tokens[0].isdigit()):
            raise ValueError("用法：/course remind <id/all> <提前分钟/off>")
        minutes = None if tokens[1] == "off" else int(tokens[1])
        changed = service.set_reminder(user_id, None if tokens[0] == "all" else int(tokens[0]), minutes)
        return f"已更新 {changed} 门课程的提醒策略。"
    if action == "delete":
        if not tokens or not tokens[0].isdigit():
            raise ValueError("用法：/course delete <id> [confirm_token]")
        course_id = int(tokens[0])
        if len(tokens) == 1:
            token = secrets.token_urlsafe(6)
            _delete_tokens[token] = (user_id, course_id, time.monotonic() + 120)
            return f"请在 2 分钟内确认：/course delete {course_id} {token}"
        expected = _delete_tokens.pop(tokens[1], None)
        if not expected or expected[:2] != (user_id, course_id) or expected[2] < time.monotonic():
            return "确认 token 无效或已过期。"
        return "已删除课程。" if service.delete(user_id, course_id) else "课程不存在。"
    raise ValueError(f"未知子命令：{action}")


def _course_changes(tokens: list[str]) -> dict:
    changes = {}
    mapping = {
        "--name": "name",
        "--teacher": "teacher",
        "--location": "location",
        "--weekday": "weekday",
        "--weeks": "weeks",
    }
    index = 0
    while index < len(tokens):
        key = tokens[index]
        if index + 1 >= len(tokens):
            raise ValueError(f"{key} 缺少值")
        value = tokens[index + 1]
        if key == "--sections":
            changes["start_section"], changes["end_section"] = parse_sections(value)
        elif key in mapping:
            changes[mapping[key]] = parse_weekday(value) if key == "--weekday" else value
        else:
            raise ValueError(f"未知字段：{key}")
        index += 2
    return changes


def _extract_subject(actor: str, tokens: list[str]) -> tuple[str, list[str]]:
    if "--user" not in tokens:
        return actor, tokens
    index = tokens.index("--user")
    if index + 1 >= len(tokens) or not tokens[index + 1].isdigit():
        raise ValueError("--user 后必须是 QQ 号")
    if get_container().permissions.role_for(actor) != PermissionLevel.SUPERUSER:
        raise ValueError("只有 SUPERUSER 可以指定 --user")
    return tokens[index + 1], tokens[:index] + tokens[index + 2 :]


def _format_course(row) -> str:
    return (
        f"#{row.course_id} 周{row.weekday} 第{row.start_section}-{row.end_section}节 {row.name}\n"
        f"  周次：{row.weeks}｜地点：{row.location or '-'}｜教师：{row.teacher or '-'}｜"
        f"提醒：{str(row.reminder_minutes) + '分钟' if row.reminder_minutes is not None else '关'}"
    )
