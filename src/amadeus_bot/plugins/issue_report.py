from __future__ import annotations

from typing import Any

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import event_group_id, onebot_message, reply_message_id
from amadeus_bot.services.issue_report import IssueReportService

command_registry.register(
    CommandSpec(
        name="issue",
        description="把疑似异常消息及附近日志保存为本地问题快照",
        usage="回复疑似异常消息后 /issue [说明]；或直接 /issue [说明] 记录命令附近内容",
        permission=PermissionLevel.SUPERUSER,
        ai_callable=False,
        examples=("回复异常回复后 /issue course 导入报错", "/issue 刚才机器人没有响应"),
        notes=(
            "优先回复具体异常消息；不回复时以本命令为时间锚点",
            "快照写入 issues/<时间-消息ID>/，包含附近消息、活动日志和运行日志",
            "仅 SUPERUSER 可用，AI 无权调用；不会下载或复制消息中的附件内容",
        ),
    )
)

issue_command = on_command("issue", permission=SUPERUSER, priority=5, block=True)


@issue_command.handle()
async def handle_issue(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    container = get_container()
    group_id = event_group_id(event)
    user_id = event.get_user_id()
    current_time = int(getattr(event, "time", 0) or 0)
    current_id = str(getattr(event, "message_id", "") or "nearby")
    command_message = _event_payload(event)
    replied_message = None
    target_id = reply_message_id(event)
    anchor_time = current_time
    anchor_id = current_id
    if target_id:
        try:
            detail = await bot.get_msg(message_id=int(target_id))
        except Exception as exc:
            await issue_command.finish(f"读取被回复消息失败：{type(exc).__name__}")
        replied_message = _api_message_payload(detail)
        anchor_time = int(detail.get("time") or current_time)
        anchor_id = str(detail.get("message_id") or target_id)
    service = IssueReportService(container.paths.project_root, container.paths.logs)
    directory = await service.capture(
        anchor_timestamp=anchor_time,
        anchor_message_id=anchor_id,
        group_id=group_id,
        user_id=user_id,
        command_message=command_message,
        replied_message=replied_message,
        note=arguments.extract_plain_text().strip(),
    )
    await issue_command.finish(f"问题快照已保存：issues/{directory.name}")


def _event_payload(event) -> dict[str, Any]:
    return {
        "message_id": str(getattr(event, "message_id", "") or ""),
        "timestamp": int(getattr(event, "time", 0) or 0),
        "user_id": event.get_user_id(),
        "group_id": event_group_id(event),
        "reply_message_id": reply_message_id(event),
        "segments": _segments(event.get_message()),
    }


def _api_message_payload(detail: dict[str, Any]) -> dict[str, Any]:
    message = onebot_message(detail.get("message"))
    sender = detail.get("sender") if isinstance(detail.get("sender"), dict) else {}
    return {
        "message_id": str(detail.get("message_id") or ""),
        "timestamp": int(detail.get("time") or 0),
        "user_id": str(sender.get("user_id") or detail.get("user_id") or ""),
        "segments": _segments(message),
    }


def _segments(message: Message) -> list[dict[str, Any]]:
    return [{"type": segment.type, "data": _json_safe(dict(segment.data))} for segment in message]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)
