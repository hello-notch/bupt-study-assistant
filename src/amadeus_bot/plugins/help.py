from __future__ import annotations

import asyncio

from nonebot import get_driver, on_command
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel, can_use_role
from amadeus_bot.plugins.common import event_group_id

command_registry.register(
    CommandSpec(
        name="help",
        description="查看按权限和群开关过滤后的帮助",
        usage="help | /help [command] | 帮助",
        aliases=("帮助",),
        permission=PermissionLevel.EVERYONE,
        ai_callable=True,
        examples=("help", "/help ddl", "帮助 course"),
        notes=("帮助图片在机器人启动时预先渲染并使用内容缓存",),
    )
)

# COMMAND_START contains an empty prefix, therefore this matcher already covers
# both ``help`` and ``/help``. Registering on_fullmatch as well runs it twice.
help_command = on_command("help", aliases={"帮助"}, priority=10, block=True)

HELP_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("基础与 AI", ("help", "chat", "history", "calc", "health", "md")),
    ("个人事务", ("ddl", "course", "memory", "privacy")),
    ("推荐", ("nowdo", "food", "music", "recommend")),
    ("群聊内容", ("stats", "summary", "quote")),
    ("群友 wife", ("wife", "changewife", "showwife", "marry")),
    ("校园服务", ("portal", "activity")),
    ("互动", ("stick", "poke")),
    (
        "开发者管理",
        ("member", "feature", "broadcast", "data", "log", "ai-cost", "ai-quota", "say"),
    ),
)


@help_command.handle()
async def handle_help(matcher: Matcher, event, arguments: Message = CommandArg()) -> None:
    target = arguments.extract_plain_text().strip()
    container = get_container()
    role = container.permissions.role_for(event.get_user_id())
    group_id = event_group_id(event)
    if target:
        spec = command_registry.get(target)
        if spec is None or not _visible(spec, role, group_id):
            await matcher.finish(f"没有找到你当前可用的命令：{target}")
        await _finish_help_image(
            matcher,
            _format_detail(spec),
            title=f"帮助 · /{spec.name}",
            variant=f"detail:{spec.name}",
        )
        return
    await _finish_help_image(
        matcher,
        _format_overview(role, group_id),
        title="邮学伴帮助",
        variant=f"overview:{role.value}",
    )


@get_driver().on_startup
async def prewarm_help_images() -> None:
    """Render overview variants and every command detail before traffic arrives."""

    container = get_container()
    group_ids = {
        str(row["scope_id"])
        for row in container.repository.get_feature_rows()
        if row.get("scope_type") == "group" and row.get("scope_id")
    }
    # The sentinel represents a group with no per-group overrides. Because the
    # renderer key includes content, ordinary groups reuse this exact image.
    scopes: tuple[str | None, ...] = (None, "__default__", *sorted(group_ids))
    jobs = []
    for role in (PermissionLevel.EVERYONE, PermissionLevel.MEMBER, PermissionLevel.SUPERUSER):
        for group_id in scopes:
            jobs.append(
                container.renderer.render_text(
                    _format_overview(role, group_id),
                    title="邮学伴帮助",
                    variant=f"overview:{role.value}",
                )
            )
    for spec in command_registry.all():
        jobs.append(
            container.renderer.render_text(
                _format_detail(spec),
                title=f"帮助 · /{spec.name}",
                variant=f"detail:{spec.name}",
            )
        )
    results = await asyncio.gather(*jobs, return_exceptions=True)
    failures = sum(isinstance(result, Exception) for result in results)
    if failures:
        logger.warning("帮助图片预渲染有 {} 项失败；/help 不会降级发送整页文字", failures)
    else:
        logger.info("帮助图片预渲染完成：{} 个缓存项", len(results))


async def _finish_help_image(matcher: Matcher, text: str, *, title: str, variant: str) -> None:
    try:
        path = await get_container().renderer.render_text(text, title=title, variant=variant)
    except Exception as exc:
        logger.exception("帮助图片渲染失败")
        await matcher.finish(f"帮助图片暂时无法生成（{type(exc).__name__}），请联系开发者查看日志。")
    await matcher.finish(MessageSegment.image(path.resolve().as_uri()))


def _format_overview(role: PermissionLevel, group_id: str | None) -> str:
    visible = [spec for spec in command_registry.all() if _visible(spec, role, group_id)]
    by_name = {spec.name: spec for spec in visible}
    lines = ["邮学伴 · 可用命令", ""]
    included: set[str] = set()
    for title, names in HELP_GROUPS:
        specs = [by_name[name] for name in names if name in by_name]
        if not specs:
            continue
        lines.append(f"【{title}】")
        for spec in specs:
            lines.extend(_overview_lines(spec))
            included.add(spec.name)
        lines.append("")
    remaining = [spec for spec in visible if spec.name not in included]
    if remaining:
        lines.append("【其他】")
        for spec in remaining:
            lines.extend(_overview_lines(spec))
        lines.append("")
    lines.extend(("使用 /help <command> 查看参数、示例、权限和规则。", "命令前的 / 可省略。"))
    return "\n".join(lines)


def _overview_lines(spec: CommandSpec) -> list[str]:
    aliases = f"（别名：{'、'.join('/' + item for item in spec.aliases)}）" if spec.aliases else ""
    ai = "可由 AI 调用" if spec.ai_callable else "仅手动命令"
    return [f"/{spec.name} {aliases}", f"  {spec.description}｜{spec.permission.value}｜{ai}"]


def _visible(spec: CommandSpec, role: PermissionLevel, group_id: str | None) -> bool:
    if spec.permission in {PermissionLevel.EVERYONE, PermissionLevel.MEMBER, PermissionLevel.SUPERUSER}:
        if not can_use_role(role, spec.permission):
            return False
    if spec.feature and group_id and not get_container().features.status(spec.feature, group_id).enabled:
        return False
    return True


def _format_detail(spec: CommandSpec) -> str:
    lines = [
        f"命令：/{spec.name}",
        f"说明：{spec.description}",
        f"用法：{spec.usage}",
        f"权限：{spec.permission.value}",
        f"AI 调用：{'是' if spec.ai_callable else '否'}",
    ]
    if spec.aliases:
        lines.append("别名：" + "、".join("/" + item for item in spec.aliases))
    if spec.examples:
        lines.append("示例：\n" + "\n".join(f"  {item}" for item in spec.examples))
    if spec.notes:
        lines.append("规则与子命令权限：\n" + "\n".join(f"  • {item}" for item in spec.notes))
    return "\n".join(lines)
