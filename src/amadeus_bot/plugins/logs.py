from __future__ import annotations

import shutil

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
        name="log",
        description="查看消息、回复、通知、AI 工具和错误活动日志",
        usage=(
            "/log [recent] [N] | status | user <QQ> [N] | group <群号> [N] | "
            "kind <inbound/outbound/notice/ai_reply/tool/error> [N] | trace <trace_id> | errors [N]"
        ),
        permission=PermissionLevel.SUPERUSER,
        feature="logs",
        ai_callable=False,
        examples=("/log", "/log recent 50", "/log user 123456789 30", "/log kind tool 20"),
        notes=(
            "人类可读日志位于 logs/activity/YYYY-MM-DD.log",
            "同目录 JSONL 文件保留结构化字段，原始群聊统计日志仍按群/日期分区",
            "仅 SUPERUSER 可通过命令查看，AI 无权调用",
        ),
    )
)

log_command = on_command("log", permission=SUPERUSER, priority=5, block=True)


@log_command.handle()
async def handle_log(arguments: Message = CommandArg()) -> None:
    tokens = arguments.extract_plain_text().split()
    action = tokens[0].lower() if tokens else "recent"
    if action in {"recent", "user", "group", "kind"}:
        try:
            rows = _activity_rows(action, tokens)
        except ValueError as exc:
            await log_command.finish(f"参数错误：{exc}")
        await finish_text_or_image(
            log_command,
            get_container().activity_log.format_rows(rows),
            title="Bot 活动日志",
            force_image=True,
        )
        return
    if action == "status":
        root = get_container().paths.logs
        file_count = sum(1 for path in root.rglob("*") if path.is_file()) if root.exists() else 0
        total_size = (
            sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) if root.exists() else 0
        )
        free = shutil.disk_usage(root if root.exists() else get_container().paths.project_root).free
        text = (
            f"日志根目录：已配置\n日志文件：{file_count}\n占用：{total_size / 1024 / 1024:.2f} MiB\n"
            f"磁盘可用：{free / 1024 / 1024 / 1024:.2f} GiB\n"
            "活动日志：logs/activity（可读 .log + 结构化 .jsonl）\n"
            "统计原始消息：logs/messages 与 logs/private"
        )
        await log_command.finish(text)
    if action == "trace" and len(tokens) == 2:
        rows = get_container().repository.audit_trace(tokens[1])
        text = (
            "\n".join(
                f"{row['created_at']} {row['command']} {row['status']} actor={row['requested_by']} "
                f"subject={row['subject_user_id'] or '-'} group={row['group_id'] or '-'}"
                for row in rows
            )
            or "没有找到该 trace_id。"
        )
        await finish_text_or_image(log_command, text, title="审计调用链")
    if action == "errors":
        limit = int(tokens[1]) if len(tokens) > 1 and tokens[1].isdigit() else 20
        rows = get_container().repository.recent_errors(limit)
        text = (
            "\n".join(
                f"#{row['error_id']} {row['created_at']} [{row['category']}] "
                f"{row['summary']} trace={row['trace_id'] or '-'}"
                for row in rows
            )
            or "没有已记录错误。"
        )
        await finish_text_or_image(log_command, text, title="最近错误")
    await log_command.finish("用法：/log recent/status/user/group/kind/trace/errors ...")


def _activity_rows(action: str, tokens: list[str]) -> list[dict]:
    service = get_container().activity_log
    if action == "recent":
        limit = _limit(tokens[1] if len(tokens) > 1 else None)
        return service.recent(limit)
    if len(tokens) < 2:
        raise ValueError(f"{action} 缺少筛选值")
    limit = _limit(tokens[2] if len(tokens) > 2 else None)
    if action == "user":
        if not tokens[1].isdigit():
            raise ValueError("QQ 号必须是数字")
        return service.recent(limit, user_id=tokens[1])
    if action == "group":
        if not tokens[1].isdigit():
            raise ValueError("群号必须是数字")
        return service.recent(limit, group_id=tokens[1])
    allowed = {"inbound", "outbound", "notice", "ai_reply", "tool", "error"}
    if tokens[1] not in allowed:
        raise ValueError("kind 必须是 " + "、".join(sorted(allowed)))
    return service.recent(limit, kind=tokens[1])


def _limit(value: str | None) -> int:
    if value is None:
        return 20
    if not value.isdigit() or not 1 <= int(value) <= 100:
        raise ValueError("N 必须是 1～100")
    return int(value)
