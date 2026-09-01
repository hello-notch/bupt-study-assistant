from __future__ import annotations

import asyncio
import json
import shlex
import time
from collections import defaultdict, deque

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import event_group_id, onebot_message, reply_message_id

for spec in (
    CommandSpec(
        name="say",
        description="诊断消息发送链路",
        usage="/say <text>",
        permission=PermissionLevel.SUPERUSER,
        ai_callable=False,
        examples=("/say 测试消息",),
        notes=("仅 SUPERUSER 可用；原样发送不超过 2000 字符的文本",),
    ),
    CommandSpec(
        name="md",
        description="把安全 Markdown 渲染为图片",
        usage="/md <markdown>；或回复文字后 /md",
        permission=PermissionLevel.EVERYONE,
        feature="render",
        ai_callable=True,
        examples=("/md # 标题", "回复一条文字后发送 /md"),
        notes=("禁止渲染外链图片和原始 HTML；图片使用内容缓存",),
    ),
    CommandSpec(
        name="stick",
        description="给被回复消息贴 QQ 表情",
        usage="回复消息后 /stick <名称/ID>；/stick list [起始ID]",
        permission=PermissionLevel.EVERYONE,
        feature="stick",
        ai_callable=True,
        ai_delegate_member=True,
        examples=("回复消息后 /stick 66", "/stick list", "/stick list 21"),
        notes=(
            "普通贴表情必须回复目标消息；可使用已验证别名或数字 emoji_id",
            "list 每次展示 20 个连续 ID 及对应的 QQ 表情消息，可传起始 ID 翻页辨认",
            "已验证别名表位于 data/shared/emoji_ids.json",
        ),
    ),
    CommandSpec(
        name="poke",
        description="戳一戳当前群友或好友",
        usage="/poke <@user/qq> [n]",
        permission=PermissionLevel.MEMBER,
        feature="poke",
        ai_callable=True,
        ai_delegate_member=True,
        examples=("/poke @某人", "/poke 123456789 3"),
        notes=("单次 1～5 次，并受发起者和目标每分钟频率限制",),
    ),
):
    command_registry.register(spec)

say_command = on_command("say", priority=5, block=True)
md_command = on_command("md", priority=10, block=True)
stick_command = on_command("stick", priority=10, block=True)
poke_command = on_command("poke", priority=10, block=True)

_poke_calls: defaultdict[str, deque[float]] = defaultdict(deque)


@say_command.handle()
async def handle_say(event, arguments: Message = CommandArg()) -> None:
    if get_container().permissions.role_for(event.get_user_id()) != PermissionLevel.SUPERUSER:
        await say_command.finish("该命令仅 SUPERUSER 可用。")
    text = arguments.extract_plain_text()
    if not text.strip() or len(text) > 2000:
        await say_command.finish("文本不能为空且不能超过 2000 字符。")
    await say_command.finish(text)


@md_command.handle()
async def handle_md(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    group_id = event_group_id(event)
    if group_id and not get_container().features.status("render", group_id).enabled:
        await md_command.finish("当前群已关闭 Markdown 渲染。")
    content = arguments.extract_plain_text().strip()
    if not content:
        message_id = reply_message_id(event)
        if message_id:
            detail = await bot.get_msg(message_id=int(message_id))
            content = onebot_message(detail.get("message")).extract_plain_text().strip()
    if not content:
        await md_command.finish("用法：/md <markdown>；也可以回复一条文字消息后发送 /md")
    try:
        path = await get_container().renderer.render_markdown(content, title="Markdown")
    except Exception as exc:
        await md_command.finish(f"图片渲染失败，已返回安全纯文本：\n{content}\n原因：{type(exc).__name__}")
    await md_command.finish(MessageSegment.image(path.resolve().as_uri()))


@stick_command.handle()
async def handle_stick(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    group_id = event_group_id(event)
    if group_id and not get_container().features.status("stick", group_id).enabled:
        await stick_command.finish("当前群已关闭贴表情功能。")
    tokens = shlex.split(arguments.extract_plain_text())
    mapping = _emoji_mapping()
    if tokens and tokens[0] == "list":
        if len(tokens) > 2 or (len(tokens) == 2 and not tokens[1].isdigit()):
            await stick_command.finish("用法：/stick list [起始ID]")
        start = int(tokens[1]) if len(tokens) == 2 else 1
        if not 1 <= start <= 999_999:
            await stick_command.finish("起始 ID 必须在 1～999999。")
        await stick_command.finish(_emoji_list_message(start))
    if len(tokens) != 1:
        await stick_command.finish("用法：回复消息后 /stick <名称/emoji_id>；或 /stick list")
    message_id = reply_message_id(event)
    if not message_id:
        await stick_command.finish("请先回复需要贴表情的消息。")
    try:
        emoji_id = _resolve_emoji_id(tokens[0], mapping)
    except ValueError as exc:
        await stick_command.finish(f"参数错误：{exc}")
    try:
        await bot.call_api("set_msg_emoji_like", message_id=int(message_id), emoji_id=int(emoji_id), set=True)
    except Exception as exc:
        await stick_command.finish(f"贴表情失败：{type(exc).__name__}；可能是 ID 不支持或消息已过期。")
    await stick_command.finish()


@poke_command.handle()
async def handle_poke(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    if not get_container().permissions.has_role(event.get_user_id(), PermissionLevel.MEMBER):
        await poke_command.finish("该命令需要 MEMBER 权限。")
    group_id = event_group_id(event)
    if group_id and not get_container().features.status("poke", group_id).enabled:
        await poke_command.finish("当前群已关闭戳一戳。")
    tokens = shlex.split(arguments.extract_plain_text())
    target = _target_user_id(arguments) or (tokens[0] if tokens and tokens[0].isdigit() else None)
    count = int(tokens[-1]) if len(tokens) > 1 and tokens[-1].isdigit() else 1
    if target is None or not 1 <= count <= 5:
        await poke_command.finish("用法：/poke <@user/qq> [1-5]")
    if not _allow_poke(event.get_user_id(), target, count):
        await poke_command.finish("操作过于频繁，请稍后再试。")
    successes = 0
    for _ in range(count):
        try:
            if group_id:
                await bot.call_api("group_poke", group_id=int(group_id), user_id=int(target))
            else:
                await bot.call_api("friend_poke", user_id=int(target))
            successes += 1
        except Exception:
            break
        if count > 1:
            await asyncio.sleep(0.7)
    await poke_command.finish(f"戳一戳完成：成功 {successes}/{count} 次。")


def _emoji_list_message(start: int) -> Message:
    message = Message()
    for emoji_id in range(start, start + 20):
        message += MessageSegment.text(f"{emoji_id} → ")
        message += MessageSegment.face(emoji_id)
        message += MessageSegment.text("\n")
    message += MessageSegment.text(f"下一组：/stick list {start + 20}")
    return message


def _emoji_mapping() -> dict:
    path = get_container().paths.data / "shared" / "emoji_ids.json"
    if not path.exists():
        return {"schema_version": 1, "items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_emoji_id(value: str, mapping: dict) -> str:
    if value.isdigit():
        return value
    lowered = value.lower()
    for item in mapping.get("items", []):
        names = {str(item.get("name", "")).lower(), *(str(a).lower() for a in item.get("aliases", []))}
        if lowered in names and item.get("status") == "verified":
            return str(item["emoji_id"])
    raise ValueError("未知表情名称；请用 /stick list 查看已验证别名，或直接提供数字 ID")


def _target_user_id(message: Message) -> str | None:
    for segment in message:
        if segment.type == "at" and str(segment.data.get("qq", "")).isdigit():
            return str(segment.data["qq"])
    return None


def _allow_poke(actor: str, target: str, count: int) -> bool:
    now = time.monotonic()
    for key in (f"actor:{actor}", f"target:{target}"):
        queue = _poke_calls[key]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) + count > 8:
            return False
    for key in (f"actor:{actor}", f"target:{target}"):
        _poke_calls[key].extend([now] * count)
    return True
