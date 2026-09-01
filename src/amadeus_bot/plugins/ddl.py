from __future__ import annotations

import secrets
import shlex
import time

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import event_group_id, finish_text_or_image
from amadeus_bot.services.ddl import format_ddl, parse_deadline

command_registry.register(
    CommandSpec(
        name="ddl",
        description="管理自己的 DDL；SUPERUSER 可用 --user 指定数据主体",
        usage=(
            "/ddl add <时间> <内容> [--remind <at/提前量/off>]；"
            "/ddl list [todo/done/all]；/ddl show/done/del <id>；"
            "/ddl edit <id> [--time <时间>] [--content <内容>]；"
            "/ddl remind <id> <at/提前量/off>"
        ),
        permission=PermissionLevel.SELF_OR_SUPERUSER,
        feature="ddl",
        ai_callable=True,
        examples=(
            "/ddl add 2分钟后 测试 --remind at",
            "/ddl add 明天下午三点 数学作业",
            "/ddl add 2026-09-02 15:00 交报告 --remind 30m",
            "/ddl list",
        ),
        notes=(
            "时间支持“2分钟后”“明天下午三点”“23:59”和“2026-09-02 15:00”",
            "仅写 23:59 表示下一次 23:59（当天已过则为次日）",
            "--remind at 表示到时提醒；30m/1小时表示提前量；off 表示不提醒",
            "省略提醒时默认提前 1 小时；距截止不足 1 小时则不设默认提醒",
        ),
    )
)

ddl_command = on_command("ddl", priority=10, block=True)
_delete_tokens: dict[str, tuple[str, int, float]] = {}


@ddl_command.handle()
async def handle_ddl(event, arguments: Message = CommandArg()) -> None:
    group_id = event_group_id(event)
    if group_id and not get_container().features.status("ddl", group_id).enabled:
        await ddl_command.finish("当前群已关闭 DDL 功能。")
    try:
        tokens = shlex.split(arguments.extract_plain_text(), posix=True)
        subject_user_id, tokens = _extract_subject(event.get_user_id(), tokens)
        if not tokens:
            raise ValueError("用法：/ddl add/list/show/edit/done/del/remind ...")
        action = tokens.pop(0).lower()
        text = _execute(action, tokens, event.get_user_id(), subject_user_id)
    except ValueError as exc:
        await ddl_command.finish(f"参数错误：{exc}")
    await finish_text_or_image(ddl_command, text, title="DDL")


def _execute(action: str, tokens: list[str], actor: str, subject: str) -> str:
    service = get_container().ddl
    if action == "add":
        deadline_text, content, reminder = _parse_add(tokens)
        created = service.add(subject, deadline_text, content, reminder=reminder)
        return f"已添加 DDL：\n{format_ddl(created.record)}\n提醒策略：{created.reminder_reason}"
    if action == "list":
        status = tokens[0] if tokens else "todo"
        items = service.list(subject, status)
        return "\n".join(format_ddl(item) for item in items) or "没有符合条件的 DDL。"
    if action == "show":
        ddl_id = _single_id(tokens, "show")
        item = service.repository.get_ddl(subject, ddl_id)
        return format_ddl(item) if item else "DDL 不存在。"
    if action == "done":
        ddl_id = _single_id(tokens, "done")
        return "已标记完成并取消未触发提醒。" if service.done(subject, ddl_id) else "DDL 不存在或已完成。"
    if action == "remind":
        if len(tokens) != 2 or not tokens[0].isdigit():
            raise ValueError("用法：/ddl remind <id> <提前量/off>")
        changed = service.set_reminder(subject, int(tokens[0]), tokens[1])
        return "提醒设置已更新。" if changed else "DDL 不存在或已完成。"
    if action == "edit":
        if not tokens or not tokens[0].isdigit():
            raise ValueError("用法：/ddl edit <id> [--time <时间>] [--content <内容>]")
        ddl_id = int(tokens.pop(0))
        deadline_text = _option_value(tokens, "--time")
        content = _option_value(tokens, "--content")
        if deadline_text is None and content is None:
            raise ValueError("至少提供 --time 或 --content")
        updated = service.edit(subject, ddl_id, deadline_text=deadline_text, content=content)
        return f"已更新 DDL：\n{format_ddl(updated)}" if updated else "DDL 不存在或已完成。"
    if action == "del":
        if not tokens or not tokens[0].isdigit():
            raise ValueError("用法：/ddl del <id> [confirm_token]")
        ddl_id = int(tokens[0])
        if len(tokens) == 1:
            item = service.repository.get_ddl(subject, ddl_id)
            if item is None:
                return "DDL 不存在。"
            token = secrets.token_urlsafe(6)
            _delete_tokens[token] = (subject, ddl_id, time.monotonic() + 120)
            return f"将删除：\n{format_ddl(item)}\n请在 2 分钟内发送 /ddl del {ddl_id} {token}"
        token = tokens[1]
        expected = _delete_tokens.pop(token, None)
        if (
            expected is None
            or expected[0] != subject
            or expected[1] != ddl_id
            or expected[2] < time.monotonic()
        ):
            return "确认 token 无效或已过期。"
        return "已删除。" if service.delete(subject, ddl_id) else "DDL 不存在。"
    raise ValueError(f"未知子命令：{action}")


def _extract_subject(actor: str, tokens: list[str]) -> tuple[str, list[str]]:
    if "--user" not in tokens:
        return str(actor), tokens
    index = tokens.index("--user")
    if index + 1 >= len(tokens) or not tokens[index + 1].isdigit():
        raise ValueError("--user 后必须是 QQ 号")
    if get_container().permissions.role_for(actor) != PermissionLevel.SUPERUSER:
        raise ValueError("只有 SUPERUSER 可以指定 --user")
    subject = tokens[index + 1]
    return subject, tokens[:index] + tokens[index + 2 :]


def _parse_add(tokens: list[str]) -> tuple[str, str, str | None]:
    reminder = None
    if "--remind" in tokens:
        index = tokens.index("--remind")
        if index + 1 >= len(tokens):
            raise ValueError("--remind 缺少提前量或 off")
        reminder = tokens[index + 1]
        tokens = tokens[:index] + tokens[index + 2 :]
    if len(tokens) < 2:
        raise ValueError("用法：/ddl add <时间> <内容> [--remind <提前量/off>]")
    for split_at in range(len(tokens) - 1, 0, -1):
        deadline_text = " ".join(tokens[:split_at])
        try:
            parse_deadline(deadline_text)
        except ValueError:
            continue
        content = " ".join(tokens[split_at:]).strip()
        if content:
            return deadline_text, content, reminder
    raise ValueError("无法从参数开头识别截止时间")


def _single_id(tokens: list[str], action: str) -> int:
    if len(tokens) != 1 or not tokens[0].isdigit():
        raise ValueError(f"用法：/ddl {action} <id>")
    return int(tokens[0])


def _option_value(tokens: list[str], name: str) -> str | None:
    if name not in tokens:
        return None
    index = tokens.index(name)
    end = len(tokens)
    for candidate in ("--time", "--content"):
        if candidate in tokens[index + 1 :]:
            end = min(end, tokens.index(candidate, index + 1))
    value = " ".join(tokens[index + 1 : end]).strip()
    if not value:
        raise ValueError(f"{name} 缺少内容")
    return value
