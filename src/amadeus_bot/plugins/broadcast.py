from __future__ import annotations

import asyncio
import shlex
import uuid

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel

command_registry.register(
    CommandSpec(
        name="broadcast",
        description="把被回复的完整消息直接广播到目标群",
        usage="回复消息后 /broadcast [--groups g1,g2] [--exclude g3] [--dry-run]",
        permission=PermissionLevel.SUPERUSER,
        ai_callable=False,
        notes=("不需要二次确认，非 dry-run 会立即发送", "默认排除命令来源群"),
    )
)

broadcast_command = on_command("broadcast", permission=SUPERUSER, priority=5, block=True)


@broadcast_command.handle()
async def handle_broadcast(bot: Bot, event: GroupMessageEvent, arguments: Message = CommandArg()) -> None:
    if event.reply is None:
        await broadcast_command.finish("请回复需要广播的消息后使用 /broadcast。")
    try:
        options = _parse_options(arguments.extract_plain_text())
    except ValueError as exc:
        await broadcast_command.finish(f"参数错误：{exc}")
    if options["groups"]:
        targets = set(options["groups"])
    else:
        group_rows = await bot.get_group_list()
        targets = {str(row["group_id"]) for row in group_rows}
    targets.discard(str(event.group_id))
    targets.difference_update(options["exclude"])
    if not targets:
        await broadcast_command.finish("没有可发送的目标群。")
    sorted_targets = sorted(targets, key=int)
    if options["dry_run"]:
        await broadcast_command.finish("广播预检完成，不发送。\n目标群：" + "、".join(sorted_targets))
    successes: list[str] = []
    failures: list[str] = []
    source_message = event.reply.message
    for group_id in sorted_targets:
        try:
            await bot.send_group_msg(group_id=int(group_id), message=source_message)
            successes.append(group_id)
        except Exception:
            await asyncio.sleep(1.0)
            try:
                await bot.send_group_msg(group_id=int(group_id), message=source_message)
                successes.append(group_id)
            except Exception:
                failures.append(group_id)
        await asyncio.sleep(0.5)
    trace_id = uuid.uuid4().hex
    get_container().repository.record_audit(
        trace_id,
        "broadcast",
        event.get_user_id(),
        "success" if not failures else "partial_failure",
        group_id=str(event.group_id),
        parameter_summary=f"targets={len(sorted_targets)},success={len(successes)},failed={len(failures)}",
    )
    lines = [
        f"广播完成：成功 {len(successes)}，失败 {len(failures)}。",
        "成功：" + ("、".join(successes) if successes else "无"),
        "失败：" + ("、".join(failures) if failures else "无"),
        f"审计 ID：{trace_id}",
    ]
    await broadcast_command.finish("\n".join(lines))


def _parse_options(raw: str) -> dict[str, object]:
    tokens = shlex.split(raw, posix=True)
    groups: set[str] = set()
    excluded: set[str] = set()
    dry_run = False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "--dry-run":
            dry_run = True
            index += 1
            continue
        if token in {"--groups", "--exclude"}:
            if index + 1 >= len(tokens):
                raise ValueError(f"{token} 缺少群号")
            values = {item.strip() for item in tokens[index + 1].split(",") if item.strip()}
            if not values or any(not item.isdigit() for item in values):
                raise ValueError(f"{token} 只能包含逗号分隔的群号")
            (groups if token == "--groups" else excluded).update(values)
            index += 2
            continue
        raise ValueError(f"未知参数 {token}")
    return {"groups": groups, "exclude": excluded, "dry_run": dry_run}
