from __future__ import annotations

import shlex

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import finish_text_or_image

command_registry.register(
    CommandSpec(
        name="member",
        description="管理 MEMBER 权限名单",
        usage="/member list | add <qq> | del <qq>",
        permission=PermissionLevel.SUPERUSER,
        ai_callable=False,
    )
)

member_command = on_command("member", permission=SUPERUSER, priority=5, block=True)


@member_command.handle()
async def handle_member(event, arguments: Message = CommandArg()) -> None:
    try:
        tokens = shlex.split(arguments.extract_plain_text())
    except ValueError as exc:
        await member_command.finish(f"参数错误：{exc}")
    repository = get_container().repository
    if not tokens or tokens[0] == "list":
        members = repository.list_members()
        text = "\n".join(members) if members else "MEMBER 名单为空。"
        await finish_text_or_image(member_command, text, title="MEMBER 名单")
    if len(tokens) != 2 or tokens[0] not in {"add", "del", "remove"} or not tokens[1].isdigit():
        await member_command.finish("用法：/member list | add <qq> | del <qq>")
    user_id = tokens[1]
    if tokens[0] == "add":
        repository.add_member(user_id, event.get_user_id())
        await member_command.finish(f"已授予 {user_id} MEMBER 权限。")
    removed = repository.remove_member(user_id)
    await member_command.finish("已移除 MEMBER 权限。" if removed else "该用户不在 MEMBER 名单中。")
