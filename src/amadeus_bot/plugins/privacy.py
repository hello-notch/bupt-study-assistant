from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel

command_registry.register(
    CommandSpec(
        name="privacy",
        description="查看或设置本人的分析与消息日志隐私开关",
        usage="/privacy status | analysis on/off | logging on/off",
        permission=PermissionLevel.EVERYONE,
        ai_callable=False,
    )
)

privacy_command = on_command("privacy", priority=10, block=True)


@privacy_command.handle()
async def handle_privacy(event, arguments: Message = CommandArg()) -> None:
    tokens = arguments.extract_plain_text().split()
    user_id = event.get_user_id()
    memory = get_container().memory
    if not tokens or tokens[0] == "status":
        await privacy_command.finish(
            f"性格分析：{'ON' if memory.analysis_enabled(user_id) else 'OFF'}\n"
            f"消息日志：{'ON' if memory.logging_enabled(user_id) else 'OFF'}\n"
            "关闭只影响此后的采集；既有记忆的查看/修改/删除仍需提交开发者申请。"
        )
    if len(tokens) != 2 or tokens[0] not in {"analysis", "logging"} or tokens[1] not in {"on", "off"}:
        await privacy_command.finish("用法：/privacy status | analysis on/off | logging on/off")
    enabled = tokens[1] == "on"
    if tokens[0] == "analysis":
        memory.set_analysis(user_id, enabled)
        if not enabled:
            request_id = get_container().repository.create_memory_request(
                user_id, "optout", "privacy command"
            )
            await privacy_command.finish(f"已关闭性格分析，并创建开发者处理申请 #{request_id}。")
    else:
        memory.set_logging(user_id, enabled)
    await privacy_command.finish(f"已将 {tokens[0]} 设为 {tokens[1]}。")
