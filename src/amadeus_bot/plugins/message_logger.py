from __future__ import annotations

from typing import Any

from nonebot import on_message, on_notice
from nonebot.adapters.onebot.v11 import Bot
from nonebot.log import logger

from amadeus_bot.bootstrap import get_container
from amadeus_bot.plugins.common import event_group_id, reply_message_id
from amadeus_bot.services.activity_log import (
    sender_label,
    summarize_message,
    summarize_notice,
)
from amadeus_bot.services.message_log import MessageLogService, MessageNormalizer

message_listener = on_message(priority=1, block=False)
notice_listener = on_notice(priority=1, block=False)
_service: MessageLogService | None = None


@message_listener.handle()
async def handle_message_log(event) -> None:
    global _service
    container = get_container()
    if not container.memory.logging_enabled(event.get_user_id()):
        return
    if _service is None:
        _service = MessageLogService(container.paths.logs)
    try:
        await _service.append(MessageNormalizer.from_onebot_event(event))
        message_summary = summarize_message(event.get_message(), reply_id=reply_message_id(event))
        summary = f"{sender_label(event)}：{message_summary}"
        await container.activity_log.record(
            "inbound",
            summary,
            user_id=event.get_user_id(),
            group_id=event_group_id(event),
            message_id=str(getattr(event, "message_id", "") or "") or None,
            details={"event": event.get_event_name()},
        )
    except Exception:
        logger.exception("记录规范化消息失败")


@notice_listener.handle()
async def handle_notice_log(event) -> None:
    container = get_container()
    notice_type, summary, user_id, group_id, details = summarize_notice(event)
    if user_id and not container.memory.logging_enabled(user_id):
        return
    try:
        await container.activity_log.record(
            "notice",
            summary,
            user_id=user_id,
            group_id=group_id,
            message_id=str(getattr(event, "message_id", "") or "") or None,
            details={"notice_type": notice_type, **details},
        )
    except Exception:
        logger.exception("记录通知事件失败")


@Bot.on_called_api
async def log_bot_api(
    bot: Bot,
    exception: Exception | None,
    api: str,
    data: dict[str, Any],
    result: Any,
) -> None:
    container = get_container()
    group_id = str(data.get("group_id") or "") or None
    user_id = str(data.get("user_id") or "") or None
    interesting = {
        "send_msg",
        "send_group_msg",
        "send_private_msg",
        "set_msg_emoji_like",
        "group_poke",
        "friend_poke",
    }
    if exception is not None:
        await container.activity_log.record(
            "error",
            f"OneBot API {api} 执行失败：{type(exception).__name__}: {exception}",
            status="failed",
            user_id=user_id or str(bot.self_id),
            group_id=group_id,
            details={"api": api, "data": _safe_api_data(api, data)},
        )
        return
    if api not in interesting:
        return
    if api.startswith("send_"):
        summary = f"Bot：{summarize_message_payload(data.get('message'))}"
        kind = "outbound"
    elif api == "set_msg_emoji_like":
        summary = (
            f"Bot {'添加' if data.get('set', True) else '移除'}消息表情："
            f"message={data.get('message_id')} emoji={data.get('emoji_id')}"
        )
        kind = "tool"
    else:
        summary = f"Bot 执行 {api}：target={data.get('user_id')}"
        kind = "tool"
    await container.activity_log.record(
        kind,
        summary,
        user_id=user_id or str(bot.self_id),
        group_id=group_id,
        message_id=_result_message_id(result),
        details={"api": api, "data": _safe_api_data(api, data)},
    )


def summarize_message_payload(value: Any) -> str:
    if value is None:
        return "[空消息]"
    if isinstance(value, str):
        return value.replace("\r", " ").replace("\n", " ↵ ")[:4000]
    try:
        return summarize_message(value)
    except (TypeError, AttributeError):
        return str(value)[:4000]


def _safe_api_data(api: str, data: dict[str, Any]) -> dict[str, Any]:
    safe = {
        key: value
        for key, value in data.items()
        if key in {"message_type", "user_id", "group_id", "message_id", "emoji_id", "set"}
    }
    if api.startswith("send_"):
        safe["message"] = summarize_message_payload(data.get("message"))
    return safe


def _result_message_id(result: Any) -> str | None:
    if isinstance(result, dict) and result.get("message_id") is not None:
        return str(result["message_id"])
    return None
