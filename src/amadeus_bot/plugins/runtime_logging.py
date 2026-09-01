from __future__ import annotations

import re
import sys
from typing import Any

from nonebot import get_driver
from nonebot.log import logger

from amadeus_bot.bootstrap import get_container

_NOISY_MESSAGES = (
    "Event will be handled by Matcher",
    "running complete",
    "Running Matcher",
    "Running CallingAPI hooks",
    "Running CalledAPI hooks",
)


@get_driver().on_startup
async def configure_compact_runtime_logging() -> None:
    """Keep startup discovery output, then switch to concise runtime logs."""

    runtime_log = get_container().paths.logs / "runtime" / "runtime.log"
    runtime_log.parent.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(
        sys.stdout,
        level="INFO",
        colorize=True,
        filter=_compact_filter,
        format=_console_format,
        backtrace=False,
        diagnose=False,
    )
    logger.add(
        runtime_log,
        level="INFO",
        colorize=False,
        filter=_compact_filter,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name} | {message}",
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
        backtrace=False,
        diagnose=False,
    )
    logger.bind(amadeus_activity=True, activity_kind="system").info(
        "简洁日志处理器已启用；详细活动记录写入 logs/activity/"
    )


def _compact_filter(record: dict[str, Any]) -> bool:
    message = str(record["message"])
    if any(fragment in message for fragment in _NOISY_MESSAGES):
        return False
    if re.search(r"\| \[(?:message|notice|request)\.", message):
        return False
    name = str(record.get("name") or "")
    if name in {"uvicorn.protocols.websockets.websockets_impl", "websockets.server"}:
        return False
    if name.startswith("uvicorn") and ("WebSocket /onebot" in message or "connection open" in message):
        return False
    return True


def _console_format(record: dict[str, Any]) -> str:
    kind = str(record["extra"].get("activity_kind") or "")
    if record["extra"].get("amadeus_activity"):
        color, label = {
            "inbound": ("cyan", "IN"),
            "outbound": ("green", "OUT"),
            "notice": ("magenta", "EVENT"),
            "ai_reply": ("blue", "AI"),
            "tool": ("yellow", "TOOL"),
            "error": ("red", "ERROR"),
            "system": ("fg #6b7280", "SYSTEM"),
        }.get(kind, ("white", kind.upper() or "LOG"))
        return f"<dim>{{time:HH:mm:ss}}</dim> <{color}>{label:>6}</{color}> │ {{message}}\n"
    level_color = "red" if record["level"].name in {"ERROR", "CRITICAL"} else "yellow"
    return (
        f"<dim>{{time:HH:mm:ss}}</dim> <{level_color}>{{level: <7}}</{level_color}>"
        " │ <dim>{name}</dim> │ {message}\n"
    )
