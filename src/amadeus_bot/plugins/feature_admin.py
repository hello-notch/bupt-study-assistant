from __future__ import annotations

import shlex
import uuid

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import event_group_id, finish_text_or_image

command_registry.register(
    CommandSpec(
        name="feature",
        description="管理全局/群功能开关和忽略用户规则",
        usage=(
            "/feature list [group_id]；/feature status <feature> [group_id]；"
            "/feature enable|disable <feature> <group_id/global>；"
            "/feature reset <feature> <group_id>；"
            "/feature ignore list|add <QQ> [group_id/global]|del <rule_id>"
        ),
        permission=PermissionLevel.SUPERUSER,
        ai_callable=False,
        examples=(
            "/feature list 123456789",
            "/feature disable proactive_chat 123456789",
            "/feature enable portal global",
            "/feature ignore add 123456789 987654321",
        ),
        notes=(
            "全部子命令仅 SUPERUSER 可用，AI 无权调用",
            "群级设置优先于全局设置；reset 删除群级覆盖并恢复全局值",
            "ignore 默认同时排除 AI 主动分析和群统计",
        ),
    )
)

feature_command = on_command("feature", permission=SUPERUSER, priority=5, block=True)


@feature_command.handle()
async def handle_feature(event, arguments: Message = CommandArg()) -> None:
    try:
        tokens = shlex.split(arguments.extract_plain_text(), posix=True)
        if not tokens:
            raise ValueError("请提供 list、status、enable、disable、reset 或 ignore")
        result = _execute(tokens, event.get_user_id(), event_group_id(event))
    except ValueError as exc:
        await feature_command.finish(f"参数错误：{exc}")
    await finish_text_or_image(feature_command, result, title="功能管理")


def _execute(tokens: list[str], actor: str, current_group_id: str | None) -> str:
    service = get_container().features
    action = tokens[0].lower()
    if action == "list":
        group_id = tokens[1] if len(tokens) > 1 else current_group_id
        if group_id is None:
            raise ValueError("私聊中必须指定 group_id")
        lines = [f"群 {group_id} 功能状态："]
        for feature in service.registered_features():
            status = service.status(feature, group_id)
            lines.append(f"{feature}: {'ON' if status.enabled else 'OFF'} ({status.source})")
        return "\n".join(lines)
    if action == "status":
        if len(tokens) < 2:
            raise ValueError("用法：/feature status <feature> [group_id]")
        group_id = tokens[2] if len(tokens) > 2 else current_group_id
        status = service.status(tokens[1], group_id)
        return f"{status.feature}: {'ON' if status.enabled else 'OFF'}，来源：{status.source}"
    if action in {"enable", "disable"}:
        if len(tokens) < 2:
            raise ValueError(f"用法：/feature {action} <feature> [group_id/global]")
        scope = tokens[2] if len(tokens) > 2 else current_group_id
        if scope is None:
            raise ValueError("私聊中必须指定 group_id 或 global")
        status = service.set(tokens[1], scope, action == "enable", actor)
        trace_id = _audit(actor, current_group_id, action, f"{tokens[1]}:{scope}:{status.enabled}")
        value = "ON" if status.enabled else "OFF"
        return f"已设置 {status.feature}={value}，来源：{status.source}\n审计 ID：{trace_id}"
    if action == "reset":
        if len(tokens) != 3:
            raise ValueError("用法：/feature reset <feature> <group_id>")
        status = service.reset(tokens[1], tokens[2])
        trace_id = _audit(actor, current_group_id, action, f"{tokens[1]}:{tokens[2]}")
        return f"已恢复全局默认：{status.feature}={'ON' if status.enabled else 'OFF'}\n审计 ID：{trace_id}"
    if action == "ignore":
        return _execute_ignore(tokens[1:], actor, current_group_id)
    raise ValueError(f"未知子命令：{action}")


def _execute_ignore(tokens: list[str], actor: str, current_group_id: str | None) -> str:
    if not tokens:
        raise ValueError("用法：/feature ignore add/del/list ...")
    repository = get_container().repository
    action = tokens[0].lower()
    if action == "list":
        rows = repository.list_ignore_rules()
        if not rows:
            return "没有忽略规则。"
        return "\n".join(
            f"#{row['rule_id']} user={row['user_id']} scope={row['scope_type']}:{row['scope_id'] or '-'} "
            f"ai={bool(row['exclude_ai'])} stats={bool(row['exclude_stats'])}"
            for row in rows
        )
    if action == "del":
        if len(tokens) != 2 or not tokens[1].isdigit():
            raise ValueError("用法：/feature ignore del <rule_id>")
        deleted = repository.delete_ignore_rule(int(tokens[1]))
        return "已删除。" if deleted else "规则不存在。"
    if action == "add":
        if len(tokens) < 2 or not tokens[1].isdigit():
            raise ValueError("用法：/feature ignore add <qq> [group_id/global]")
        scope = tokens[2] if len(tokens) > 2 else current_group_id
        if scope is None:
            raise ValueError("私聊中必须指定 group_id 或 global")
        if scope == "global":
            scope_type, scope_id = "global", ""
        elif scope.isdigit():
            scope_type, scope_id = "group", scope
        else:
            raise ValueError("作用域必须是群号或 global")
        rule_id = repository.add_ignore_rule(tokens[1], scope_type, scope_id, actor)
        return f"已添加/更新忽略规则 #{rule_id}：AI 与统计均排除。"
    raise ValueError(f"未知 ignore 子命令：{action}")


def _audit(actor: str, group_id: str | None, command: str, summary: str) -> str:
    trace_id = uuid.uuid4().hex
    get_container().repository.record_audit(
        trace_id,
        f"feature.{command}",
        actor,
        "success",
        group_id=group_id,
        parameter_summary=summary,
    )
    return trace_id
