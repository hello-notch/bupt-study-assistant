from __future__ import annotations

import secrets
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import event_group_id

SHANGHAI = ZoneInfo("Asia/Shanghai")

for spec in (
    CommandSpec(
        name="wife",
        description="抽取当前群今日群友 wife",
        usage="/wife",
        permission=PermissionLevel.EVERYONE,
        feature="wife",
        ai_callable=True,
        examples=("/wife",),
        notes=(
            "只在真实群聊中可用，临时会话和普通私聊不可用",
            "配对以群为作用域，同一对群友当天互相对应",
            "每日北京时间 0 点进入新的一天并重新允许抽取",
            "不会把机器人和 NapCat 标记为机器人的群成员放入候选池",
        ),
    ),
    CommandSpec(
        name="changewife",
        description="按次数限制更换今日 wife",
        usage="/changewife",
        permission=PermissionLevel.EVERYONE,
        feature="wife",
        ai_callable=True,
        examples=("/changewife",),
        notes=("更换次数受当日规则限制；新配对仍保持双方对称",),
    ),
    CommandSpec(
        name="marry",
        description="向当前群友发起或确认结婚",
        usage="/marry <@user/qq> | confirm <token>",
        permission=PermissionLevel.EVERYONE,
        feature="wife",
        ai_callable=True,
        examples=("/marry @某人", "/marry 123456789", "/marry confirm <token>"),
        notes=("目标必须是当前群成员且不能是自己", "确认 token 仅目标本人可用，5 分钟后过期"),
    ),
    CommandSpec(
        name="showwife",
        description="查看当前群今日配对",
        usage="/showwife [@user/qq]",
        permission=PermissionLevel.EVERYONE,
        feature="wife",
        ai_callable=True,
        examples=("/showwife", "/showwife @某人"),
        notes=("不指定用户时查看自己；只能查询当前群当天的配对",),
    ),
):
    command_registry.register(spec)

wife_command = on_command("wife", priority=10, block=True)
change_command = on_command("changewife", priority=10, block=True)
marry_command = on_command("marry", priority=10, block=True)
show_command = on_command("showwife", priority=10, block=True)

_marry_tokens: dict[str, tuple[str, str, str, float]] = {}


@wife_command.handle()
async def handle_wife(bot: Bot, event) -> None:
    group_id = await _require_group_enabled(event, wife_command)
    members = await _candidate_ids(bot, group_id)
    try:
        pair = get_container().group_repository.assign_wife(
            group_id, event.get_user_id(), members, datetime.now(SHANGHAI).date()
        )
    except ValueError as exc:
        await wife_command.finish(str(exc))
    name = await _member_name(bot, group_id, pair.partner_id)
    message = Message(
        [
            MessageSegment.text(f"你今天的群友 wife 是：{name}（{pair.partner_id}）\n"),
            MessageSegment.image(_avatar_url(pair.partner_id)),
        ]
    )
    await wife_command.finish(message)


@change_command.handle()
async def handle_change(bot: Bot, event) -> None:
    group_id = await _require_group_enabled(event, change_command)
    members = await _candidate_ids(bot, group_id)
    try:
        pair = get_container().group_repository.assign_wife(
            group_id, event.get_user_id(), members, datetime.now(SHANGHAI).date(), replace=True
        )
    except ValueError as exc:
        await change_command.finish(str(exc))
    name = await _member_name(bot, group_id, pair.partner_id)
    await change_command.finish(
        Message(
            [
                MessageSegment.text(
                    f"已更换为：{name}（{pair.partner_id}）\n今日已更换 {pair.changes} 次。\n"
                ),
                MessageSegment.image(_avatar_url(pair.partner_id)),
            ]
        )
    )


@show_command.handle()
async def handle_show(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    group_id = await _require_group_enabled(event, show_command)
    target = _at_user(arguments) or arguments.extract_plain_text().strip() or event.get_user_id()
    if not target.isdigit():
        await show_command.finish("用法：/showwife [@user/qq]")
    pair = get_container().group_repository.get_wife(group_id, target, datetime.now(SHANGHAI).date())
    if pair is None:
        await show_command.finish("该群友今天还没有配对。")
    target_name = await _member_name(bot, group_id, target)
    partner_name = await _member_name(bot, group_id, pair.partner_id)
    await show_command.finish(f"{target_name} 今日的 wife：{partner_name}（{pair.partner_id}）")


@marry_command.handle()
async def handle_marry(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    group_id = await _require_group_enabled(event, marry_command)
    text = arguments.extract_plain_text().strip()
    if text.startswith("confirm "):
        token = text.split(maxsplit=1)[1]
        pending = _marry_tokens.pop(token, None)
        if pending is None or pending[3] < time.monotonic():
            await marry_command.finish("确认 token 无效或已过期。")
        source_group, proposer, target, _ = pending
        if source_group != group_id or target != event.get_user_id():
            await marry_command.finish("该确认请求不属于你或不属于当前群。")
        try:
            pair = get_container().group_repository.marry(
                group_id, proposer, target, datetime.now(SHANGHAI).date()
            )
        except ValueError as exc:
            await marry_command.finish(str(exc))
        await marry_command.finish(f"结婚成功：{pair.user_id} ↔ {pair.partner_id}")
    target = _at_user(arguments) or text
    if not target.isdigit() or target == event.get_user_id():
        await marry_command.finish("用法：/marry <@user/qq>")
    member_ids = await _candidate_ids(bot, group_id, include_paired=True)
    if target not in member_ids:
        await marry_command.finish("目标不是当前群成员。")
    token = secrets.token_urlsafe(6)
    _marry_tokens[token] = (group_id, event.get_user_id(), target, time.monotonic() + 300)
    await marry_command.finish(f"已向 {target} 发起结婚请求。对方请在 5 分钟内发送：/marry confirm {token}")


async def _require_group_enabled(event, matcher) -> str:
    group_id = event_group_id(event)
    if not group_id:
        await matcher.finish("该功能只能在群聊中使用。")
    if not get_container().features.status("wife", group_id).enabled:
        await matcher.finish("当前群已关闭 wife 功能。")
    return group_id


async def _candidate_ids(bot: Bot, group_id: str, *, include_paired: bool = False) -> list[str]:
    members = await bot.get_group_member_list(group_id=int(group_id))
    result = []
    for member in members:
        user_id = str(member.get("user_id", ""))
        if not user_id.isdigit() or user_id == str(bot.self_id) or member.get("is_robot"):
            continue
        if not include_paired:
            pair = get_container().group_repository.get_wife(group_id, user_id, datetime.now(SHANGHAI).date())
            if pair:
                continue
        result.append(user_id)
    return result


async def _member_name(bot: Bot, group_id: str, user_id: str) -> str:
    try:
        member = await bot.get_group_member_info(group_id=int(group_id), user_id=int(user_id))
    except Exception:
        return user_id
    return str(member.get("card") or member.get("nickname") or user_id)


def _at_user(message: Message) -> str | None:
    for segment in message:
        if segment.type == "at" and str(segment.data.get("qq", "")).isdigit():
            return str(segment.data["qq"])
    return None


def _avatar_url(user_id: str) -> str:
    return f"https://q1.qlogo.cn/g?b=qq&nk={user_id}&s=640"
