from __future__ import annotations

import json
import shlex

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import (
    event_group_id,
    finish_text_or_image,
    onebot_message,
    reply_message_id,
)
from amadeus_bot.services.campus import ActivitySource, PortalSource

for spec in (
    CommandSpec(
        name="portal",
        description="查询和订阅北邮信息门户校内通知",
        usage="/portal [N] | search <关键词> [N] | sub on/off | group-sub on/off | refresh",
        permission=PermissionLevel.EVERYONE,
        feature="portal",
        ai_callable=True,
        examples=("/portal 5", "/portal search 奖学金 10", "/portal sub on"),
        notes=(
            "N 最大为 20；不写参数时显示最近 10 条缓存通知",
            "sub 管理本人每日私聊推送；group-sub 和 refresh 仅 SUPERUSER 可用",
            "列表来自只读抓取缓存，登录失效时可由 Playwright 自动续登",
        ),
    ),
    CommandSpec(
        name="activity",
        description="只读查询和订阅北邮第二课堂活动",
        usage="/activity [N] [--category c] [--campus c] | search <关键词> | sub/group-sub on/off",
        permission=PermissionLevel.EVERYONE,
        feature="activity",
        ai_callable=True,
        examples=(
            "/activity 10 --campus 西土城",
            "/activity search 讲座",
            "/activity sub on --category 讲座",
        ),
        notes=(
            "N 最大为 20；--category 和 --campus 只筛选已抓取缓存",
            "sub 管理本人每日私聊推送；group-sub、refresh 和 import-file 仅 SUPERUSER 可用",
            "import-file 必须回复 JSON/CSV 文件，是在线数据源不可用时的只读降级方案",
            "机器人永远不会自动报名、签到或退选，AI 也无权执行这些操作",
        ),
    ),
):
    command_registry.register(spec)

portal_command = on_command("portal", priority=10, block=True)
activity_command = on_command("activity", priority=10, block=True)


@portal_command.handle()
async def handle_portal(event, arguments: Message = CommandArg()) -> None:
    await _handle_source("portal", portal_command, event, arguments)


@activity_command.handle()
async def handle_activity(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    tokens = shlex.split(arguments.extract_plain_text())
    if tokens and tokens[0] == "import-file":
        if get_container().permissions.role_for(event.get_user_id()) != PermissionLevel.SUPERUSER:
            await activity_command.finish("活动导入仅 SUPERUSER 可用。")
        reply_id = reply_message_id(event)
        if not reply_id:
            await activity_command.finish("请回复一个 JSON/CSV 文件后使用 /activity import-file。")
        detail = await bot.get_msg(message_id=int(reply_id))
        message = onebot_message(detail.get("message"))
        segment = next((item for item in message if item.type == "file"), None)
        if segment is None:
            await activity_command.finish("被回复消息中没有文件。")
        url = segment.data.get("url")
        if not url:
            await activity_command.finish("该文件没有可下载 URL。")
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(str(url))
            response.raise_for_status()
        total, new_count = ActivitySource(get_container().repository).import_file(
            response.content, str(segment.data.get("name") or segment.data.get("file") or "")
        )
        await activity_command.finish(f"已导入 {total} 条活动，其中新增 {new_count} 条。")
    await _handle_source("activity", activity_command, event, arguments)


async def _handle_source(source: str, matcher, event, arguments: Message) -> None:
    group_id = event_group_id(event)
    if group_id and not get_container().features.status(source, group_id).enabled:
        await matcher.finish("当前群已关闭该校园数据源。")
    try:
        tokens = shlex.split(arguments.extract_plain_text())
    except ValueError as exc:
        await matcher.finish(f"参数错误：{exc}")
    if tokens and tokens[0] == "refresh":
        if get_container().permissions.role_for(event.get_user_id()) != PermissionLevel.SUPERUSER:
            await matcher.finish("手动刷新仅 SUPERUSER 可用。")
        adapter = (
            PortalSource(get_container().repository)
            if source == "portal"
            else ActivitySource(get_container().repository)
        )
        try:
            total, new_count = await adapter.refresh()
        except Exception as exc:
            get_container().repository.set_source_health(source, success=False, error_summary=str(exc))
            await matcher.finish(f"刷新失败：{exc}")
        await matcher.finish(f"刷新完成：取得 {total} 条，其中新增 {new_count} 条。")
    if tokens and tokens[0] in {"sub", "group-sub"}:
        await _subscription(source, matcher, event, tokens)
        return
    query = ""
    limit = 10
    if tokens and tokens[0] == "search":
        if len(tokens) < 2:
            await matcher.finish(f"用法：/{source} search <关键词> [N]")
        query = tokens[1]
        if len(tokens) > 2 and tokens[2].isdigit():
            limit = min(20, int(tokens[2]))
    elif tokens and tokens[0].isdigit():
        limit = min(20, int(tokens[0]))
    rows = get_container().repository.query_source_items(source, query, limit)
    if source == "activity":
        category = _option(tokens, "--category")
        campus = _option(tokens, "--campus")
        rows = [row for row in rows if _metadata_matches(row, category, campus)]
    if not rows:
        health = get_container().repository.get_source_health(source)
        if (
            source == "activity"
            and health
            and health.get("last_success_at")
            and not int(health.get("consecutive_failures") or 0)
        ):
            if int(health.get("item_count") or 0) == 0:
                await matcher.finish("当前第二课堂没有活动。")
            await matcher.finish("没有符合当前筛选条件的第二课堂活动。")
        suffix = (
            f"最近状态：{health['error_summary']}"
            if health and health["error_summary"]
            else "请让 SUPERUSER 先 refresh。"
        )
        await matcher.finish("暂无缓存数据。" + suffix)
    text = "\n\n".join(_format_source_item(source, row) for row in rows)
    if source == "portal":
        # Portal entries contain actionable URLs, so they must remain clickable.
        await matcher.finish(text)
    await finish_text_or_image(
        matcher,
        text,
        title="第二课堂",
        force_image=True,
    )


async def _subscription(source: str, matcher, event, tokens: list[str]) -> None:
    action = tokens[0]
    if len(tokens) < 2 or tokens[1] not in {"on", "off"}:
        await matcher.finish(f"用法：/{source} {action} on/off")
    if action == "group-sub":
        if get_container().permissions.role_for(event.get_user_id()) != PermissionLevel.SUPERUSER:
            await matcher.finish("群订阅仅 SUPERUSER 可配置。")
        scope_type, scope_id = "group", event_group_id(event)
        if not scope_id:
            await matcher.finish("group-sub 必须在群聊中使用。")
    else:
        scope_type, scope_id = "user", event.get_user_id()
    filters = {"category": _option(tokens, "--category"), "campus": _option(tokens, "--campus")}
    get_container().repository.set_subscription(
        source, scope_type, scope_id, tokens[1] == "on", event.get_user_id(), filters
    )
    await matcher.finish(f"已将 {source} {scope_type} 订阅设为 {tokens[1]}。")


def _format_source_item(source: str, row: dict) -> str:
    metadata = json.loads(row.get("metadata") or "{}")
    extra = ""
    if source == "activity":
        extra = (
            f"\n类别：{metadata.get('category') or '-'}｜校区：{metadata.get('campus') or '-'}"
            f"｜地点：{metadata.get('location') or '-'}｜状态：{metadata.get('status') or '-'}"
        )
    return (
        f"{row['title']}\n{row.get('department') or '-'}｜{row.get('published_at') or '时间未知'}"
        f"{extra}\n{row.get('summary') or ''}\n{row.get('url') or ''}"
    ).strip()


def _metadata_matches(row: dict, category: str | None, campus: str | None) -> bool:
    metadata = json.loads(row.get("metadata") or "{}")
    return (not category or category in str(metadata.get("category", ""))) and (
        not campus or campus in str(metadata.get("campus", ""))
    )


def _option(tokens: list[str], name: str) -> str | None:
    if name not in tokens:
        return None
    index = tokens.index(name)
    return tokens[index + 1] if index + 1 < len(tokens) else None
