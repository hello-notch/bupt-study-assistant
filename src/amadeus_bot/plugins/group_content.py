from __future__ import annotations

import hashlib
import secrets
import shlex
import time

import httpx
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.ai import AITask
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import (
    event_group_id,
    finish_text_or_image,
    onebot_message,
    reply_message_id,
)
from amadeus_bot.services.analytics import AnalyticsService, format_deterministic

for spec in (
    CommandSpec(
        name="stats",
        description="统计当前群最近 N 小时的水群数据",
        usage="/stats [1-24] [@user]",
        permission=PermissionLevel.EVERYONE,
        feature="stats",
        ai_callable=True,
    ),
    CommandSpec(
        name="summary",
        description="总结当前群最近 N 小时",
        usage="/summary [1-24]",
        permission=PermissionLevel.EVERYONE,
        feature="summary",
        ai_callable=True,
    ),
    CommandSpec(
        name="quote",
        description="收藏、查询和管理当前群群友语录",
        usage="回复消息 /quote add [name]；/quote list/find/show/random/edit/delete ...",
        permission=PermissionLevel.EVERYONE,
        feature="quotes",
        ai_callable=True,
    ),
):
    command_registry.register(spec)

stats_command = on_command("stats", priority=10, block=True)
summary_command = on_command("summary", priority=10, block=True)
quote_command = on_command("quote", priority=10, block=True)

_quote_delete_tokens: dict[str, tuple[str, int, str, float]] = {}


@stats_command.handle()
async def handle_stats(event, arguments: Message = CommandArg()) -> None:
    group_id = await _require_group(event, stats_command, "stats")
    tokens = arguments.extract_plain_text().split()
    hours = int(tokens[0]) if tokens and tokens[0].isdigit() else 1
    target = _at_user(arguments)
    if target and get_container().features.is_ignored(target, group_id, "stats"):
        await stats_command.finish("该用户已退出统计/性格分析。")
    service = AnalyticsService(get_container().paths.logs)
    try:
        window = service.load_group(group_id, hours)
    except ValueError as exc:
        await stats_command.finish(f"参数错误：{exc}")
    deterministic = service.deterministic(window, target)
    base = "【确定性统计】\n" + format_deterministic(window, deterministic)
    transcript = service.ai_transcript(window)
    if deterministic["messages"] < 3 or not transcript:
        await finish_text_or_image(stats_command, base + "\n\n样本不足，未调用 AI 分析。", title="水群统计")
    if target and not get_container().memory.analysis_enabled(target):
        await finish_text_or_image(stats_command, base + "\n\n该用户已退出性格分析。", title="水群统计")
    prompt = (
        "分析以下群聊时间窗。只描述该时段，不做永久人格判断。输出：主要话题、高频表达、活跃特点、"
        "样本量、置信度。不得编造统计数字。\n\n" + transcript
    )
    try:
        result = await get_container().ai.complete(
            AITask.STATS_ANALYSIS,
            [{"role": "user", "content": prompt}],
            group_id=group_id,
            user_id=event.get_user_id(),
        )
        analysis = result.content.strip()
    except Exception:
        analysis = "AI 分析暂不可用；确定性统计不受影响。"
    await finish_text_or_image(
        stats_command,
        base + "\n\n【AI 分析（仅代表该时段）】\n" + analysis,
        title="水群统计",
        force_image=True,
    )


@summary_command.handle()
async def handle_summary(event, arguments: Message = CommandArg()) -> None:
    group_id = await _require_group(event, summary_command, "summary")
    text = arguments.extract_plain_text().strip()
    if text and not text.isdigit():
        await summary_command.finish("用法：/summary [1-24]")
    hours = int(text or "1")
    service = AnalyticsService(get_container().paths.logs)
    try:
        window = service.load_group(group_id, hours)
    except ValueError as exc:
        await summary_command.finish(f"参数错误：{exc}")
    transcript = service.ai_transcript(window, max_chars=24_000)
    if len(window.effective_records) < 3 or len(transcript) < 30:
        await summary_command.finish("有效消息不足，未调用 AI 总结。")
    prompt = (
        "总结以下群聊，输出：主要话题、结论/决定、待办、链接/资料、未解决问题、轻松时刻。"
        "不要泄露其他群信息，不要编造。\n\n" + transcript
    )
    try:
        result = await get_container().ai.complete(
            AITask.SUMMARY,
            [{"role": "user", "content": prompt}],
            group_id=group_id,
            user_id=event.get_user_id(),
        )
    except Exception:
        await summary_command.finish("AI 总结服务暂不可用。")
    heading = (
        f"时间：{window.start:%Y-%m-%d %H:%M} ～ {window.end:%Y-%m-%d %H:%M}\n"
        f"有效消息：{len(window.effective_records)}\n\n"
    )
    await finish_text_or_image(
        summary_command,
        heading + result.content.strip(),
        title="群聊总结",
        force_image=True,
    )


@quote_command.handle()
async def handle_quote(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    group_id = await _require_group(event, quote_command, "quotes")
    try:
        tokens = shlex.split(arguments.extract_plain_text())
        if not tokens:
            raise ValueError("用法：/quote add/list/find/show/random/edit/delete ...")
        action = tokens.pop(0).lower()
        if action == "add":
            await _quote_add(bot, event, group_id, tokens)
            return
        text = _quote_execute(event.get_user_id(), group_id, action, tokens)
    except ValueError as exc:
        await quote_command.finish(f"参数错误：{exc}")
    await finish_text_or_image(quote_command, text, title="群友语录")


async def _quote_add(bot: Bot, event, group_id: str, tokens: list[str]) -> None:
    message_id = reply_message_id(event)
    if not message_id:
        await quote_command.finish("请回复一条文字或图片消息后使用 /quote add。")
    detail = await bot.get_msg(message_id=int(message_id))
    message = onebot_message(detail.get("message"))
    text = message.extract_plain_text().strip()
    name, tags = _name_tags(tokens)
    media = await _save_quote_media(group_id, message)
    if not text and not media:
        await quote_command.finish("被回复消息没有可收藏的文字或图片。")
    source_author = str((detail.get("sender") or {}).get("user_id") or detail.get("user_id") or "")
    record = get_container().group_repository.add_quote(
        group_id, message_id, source_author, event.get_user_id(), name, tags, text, media
    )
    await quote_command.finish(
        f"已收藏语录 #{record.quote_id}\n作者：{record.source_author_id}\n名称：{record.name or '未命名'}"
    )


def _quote_execute(actor: str, group_id: str, action: str, tokens: list[str]) -> str:
    repository = get_container().group_repository
    if action in {"list", "find"}:
        query = " ".join(tokens) if action == "find" else ""
        rows = repository.list_quotes(group_id, query)
        return "\n".join(_format_quote(row, brief=True) for row in rows[:50]) or "没有匹配语录。"
    if action == "random":
        row = repository.random_quote(group_id, " ".join(tokens))
        return _format_quote(row) if row else "没有匹配语录。"
    if action == "show":
        quote_id = _quote_id(tokens, "show")
        row = repository.get_quote(group_id, quote_id)
        return _format_quote(row) if row else "语录不存在。"
    if action == "edit":
        if not tokens or not tokens[0].isdigit():
            raise ValueError("用法：/quote edit <id> [--name ...] [--tags ...]")
        row = repository.get_quote(group_id, int(tokens.pop(0)))
        if row is None:
            return "语录不存在。"
        _require_quote_manage(actor, row)
        name, tags = _name_tags(tokens, default_name=row.name, default_tags=row.tags)
        repository.edit_quote(group_id, row.quote_id, name, tags)
        return f"已更新语录 #{row.quote_id}。"
    if action == "delete":
        if not tokens or not tokens[0].isdigit():
            raise ValueError("用法：/quote delete <id> [confirm_token]")
        quote_id = int(tokens[0])
        row = repository.get_quote(group_id, quote_id)
        if row is None:
            return "语录不存在。"
        _require_quote_manage(actor, row)
        if len(tokens) == 1:
            token = secrets.token_urlsafe(6)
            _quote_delete_tokens[token] = (group_id, quote_id, actor, time.monotonic() + 120)
            return f"将删除语录 #{quote_id}。请在 2 分钟内发送 /quote delete {quote_id} {token}"
        expected = _quote_delete_tokens.pop(tokens[1], None)
        if not expected or expected[:3] != (group_id, quote_id, actor) or expected[3] < time.monotonic():
            return "确认 token 无效或已过期。"
        return "已删除。" if repository.delete_quote(group_id, quote_id) else "语录不存在。"
    raise ValueError(f"未知子命令：{action}")


async def _save_quote_media(group_id: str, message: Message) -> tuple[dict[str, str], ...]:
    directory = get_container().paths.data / "groups" / group_id / "media" / "quotes"
    saved = []
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        for segment in message:
            if segment.type != "image" or not segment.data.get("url"):
                continue
            try:
                response = await client.get(str(segment.data["url"]))
                response.raise_for_status()
                data = response.content
            except Exception:
                continue
            if len(data) > 10 * 1024 * 1024:
                continue
            digest = hashlib.sha256(data).hexdigest()
            suffix = ".gif" if response.headers.get("content-type", "").startswith("image/gif") else ".jpg"
            path = directory / f"{digest}{suffix}"
            directory.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(data)
            saved.append({"path": str(path.relative_to(get_container().paths.data)), "sha256": digest})
    return tuple(saved)


async def _require_group(event, matcher, feature: str) -> str:
    group_id = event_group_id(event)
    if not group_id:
        await matcher.finish("该功能只能在群聊中使用。")
    if not get_container().features.status(feature, group_id).enabled:
        await matcher.finish("当前群已关闭该功能。")
    return group_id


def _at_user(message: Message) -> str | None:
    for segment in message:
        if segment.type == "at" and str(segment.data.get("qq", "")).isdigit():
            return str(segment.data["qq"])
    return None


def _name_tags(
    tokens: list[str], *, default_name: str = "", default_tags: tuple[str, ...] = ()
) -> tuple[str, tuple[str, ...]]:
    name = default_name
    tags = default_tags
    if "--tags" in tokens:
        index = tokens.index("--tags")
        if index + 1 >= len(tokens):
            raise ValueError("--tags 缺少内容")
        tags = tuple(item for item in tokens[index + 1].split(",") if item)
        tokens = tokens[:index]
    if "--name" in tokens:
        index = tokens.index("--name")
        name = " ".join(tokens[index + 1 :]).strip()
    elif tokens:
        name = " ".join(tokens).strip()
    return name, tags


def _quote_id(tokens: list[str], action: str) -> int:
    if len(tokens) != 1 or not tokens[0].isdigit():
        raise ValueError(f"用法：/quote {action} <id>")
    return int(tokens[0])


def _require_quote_manage(actor: str, row) -> None:
    if actor in {row.saved_by_id, row.source_author_id}:
        return
    if get_container().permissions.has_role(actor, PermissionLevel.MEMBER):
        return
    raise ValueError("只有保存者、原作者或 MEMBER 可以管理该语录")


def _format_quote(row, *, brief: bool = False) -> str:
    if row is None:
        return "语录不存在。"
    content = row.text.replace("\n", " ")[:100] if brief else row.text
    media = f" [图片 {len(row.media_refs)}]" if row.media_refs else ""
    return (
        f"#{row.quote_id} {row.name or '未命名'} · 作者 {row.source_author_id}\n"
        f"{content or '[图片语录]'}{media}\n标签：{','.join(row.tags) or '-'}"
    )
