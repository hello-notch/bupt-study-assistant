from __future__ import annotations

import shlex

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import event_group_id, finish_text_or_image

POOL_NAMES = {"activity": "干什么", "food": "吃什么", "music": "推歌"}

for spec in (
    CommandSpec(
        name="nowdo",
        aliases=("干什么",),
        description="从普通事项、食物、歌曲和本人未完成 DDL 中随机推荐",
        usage="/nowdo [path]",
        permission=PermissionLevel.EVERYONE,
        feature="recommendation",
        ai_callable=True,
        examples=("/nowdo", "/干什么 学习"),
        notes=("候选来自事项、食物、歌曲三个独立池以及本人未完成 DDL",),
    ),
    CommandSpec(
        name="food",
        aliases=("吃什么",),
        description="只从食物池随机推荐",
        usage="/food [tag]",
        permission=PermissionLevel.EVERYONE,
        feature="recommendation",
        ai_callable=True,
        examples=("/food", "/吃什么 西土城"),
        notes=("只使用 food 食物池，不会混入事项、歌曲或 DDL",),
    ),
    CommandSpec(
        name="music",
        aliases=("推歌", "听什么"),
        description="只从歌曲池随机推荐",
        usage="/music [tag]",
        permission=PermissionLevel.EVERYONE,
        feature="recommendation",
        ai_callable=True,
        examples=("/music", "/听什么 古典", "/推歌"),
        notes=("只使用 music 歌曲池；普通回复不显示数据库条目编号",),
    ),
    CommandSpec(
        name="recommend",
        description="查看或维护独立推荐池",
        usage="/recommend list <pool> [path] | add <pool> <path> <content> | del <id>",
        permission=PermissionLevel.EVERYONE,
        feature="recommendation",
        ai_callable=True,
        ai_delegate_member=True,
        examples=(
            "/recommend list food",
            "/recommend add music - 命运石之门主题曲",
            "/recommend del 12",
        ),
        notes=(
            "pool 必须是 activity、food 或 music，三个推荐池互相独立",
            "list 所有人可用；add 需要 MEMBER；删除仅限本人条目或可管理共享内容者",
        ),
    ),
):
    command_registry.register(spec)

nowdo_command = on_command("nowdo", aliases={"干什么"}, priority=10, block=True)
food_command = on_command("food", aliases={"吃什么"}, priority=10, block=True)
music_command = on_command("music", aliases={"推歌", "听什么"}, priority=10, block=True)
recommend_command = on_command("recommend", priority=10, block=True)


@nowdo_command.handle()
async def handle_nowdo(event, arguments: Message = CommandArg()) -> None:
    await _ensure_enabled(event, nowdo_command)
    path = arguments.extract_plain_text().strip()
    available = []
    repository = get_container().repository
    for pool in ("activity", "food", "music"):
        item = repository.choose_recommendation(pool, path)
        if item:
            available.append(item)
    ddl_items = get_container().ddl.list(event.get_user_id(), "todo")
    if not available and not ddl_items:
        await nowdo_command.finish("当前路径没有可推荐的事项。")
    import random

    if ddl_items and (not available or random.randrange(len(available) + 1) == len(available)):
        ddl = random.choice(ddl_items)
        await nowdo_command.finish(f"既然还没决定，不如先推进一下这个 DDL：\n{ddl.content}")
    item = random.choice(available)
    await nowdo_command.finish(_friendly_recommendation(item.pool, item.content, nowdo=True))


@food_command.handle()
async def handle_food(event, arguments: Message = CommandArg()) -> None:
    await _ensure_enabled(event, food_command)
    await _finish_random(food_command, "food", arguments.extract_plain_text().strip())


@music_command.handle()
async def handle_music(event, arguments: Message = CommandArg()) -> None:
    await _ensure_enabled(event, music_command)
    await _finish_random(music_command, "music", arguments.extract_plain_text().strip())


async def _finish_random(matcher, pool: str, path: str) -> None:
    item = get_container().repository.choose_recommendation(pool, path)
    if item is None:
        empty_text = {
            "activity": "暂时想不到合适的事——推荐池还是空的，等 MEMBER 添几条吧。",
            "food": "今天的菜单还没准备好，食物推荐池里暂时没有内容。",
            "music": "歌单还是空的，暂时没法认真给你推荐。",
        }
        await matcher.finish(empty_text[pool])
    await matcher.finish(_friendly_recommendation(pool, item.content))


@recommend_command.handle()
async def handle_recommend(event, arguments: Message = CommandArg()) -> None:
    await _ensure_enabled(event, recommend_command)
    try:
        tokens = shlex.split(arguments.extract_plain_text(), posix=True)
    except ValueError as exc:
        await recommend_command.finish(f"参数错误：{exc}")
    if not tokens:
        await recommend_command.finish("用法：/recommend list <pool> [path] | add ... | del <id>")
    action = tokens[0].lower()
    if action == "list":
        if len(tokens) < 2:
            await recommend_command.finish("用法：/recommend list <activity/food/music> [path]")
        pool = _validate_pool(tokens[1])
        path = tokens[2] if len(tokens) > 2 else ""
        items = get_container().repository.list_recommendations(pool, path)
        text = (
            "\n".join(
                f"#{item.recommendation_id} [{item.path or '根'}] {item.content} (w={item.weight:g})"
                for item in items
            )
            or "没有条目。"
        )
        await finish_text_or_image(recommend_command, text, title=f"{POOL_NAMES[pool]}推荐池")
        return
    if action == "add":
        if not get_container().permissions.has_role(event.get_user_id(), PermissionLevel.MEMBER):
            await recommend_command.finish("该操作需要 MEMBER 权限；AI 委托入口将在工具层单独授权。")
        try:
            pool, path, content, weight, tags = _parse_add(tokens[1:])
        except ValueError as exc:
            await recommend_command.finish(f"参数错误：{exc}")
        item_id = get_container().repository.add_recommendation(
            pool, path, content, weight, tags, event.get_user_id()
        )
        await recommend_command.finish(
            f"已添加 #{item_id} 到 {POOL_NAMES[pool]} 池。\n路径：{path or '根'}\n内容：{content}"
        )
    if action == "del":
        if len(tokens) != 2 or not tokens[1].isdigit():
            await recommend_command.finish("用法：/recommend del <id>")
        repository = get_container().repository
        item = repository.get_recommendation(int(tokens[1]))
        if item is None:
            await recommend_command.finish("条目不存在或已删除。")
        if not get_container().permissions.can_manage_recommendation(event.get_user_id(), item.creator_id):
            await recommend_command.finish("只能删除自己的条目；MEMBER 可管理共享内容。")
        repository.delete_recommendation(item.recommendation_id)
        await recommend_command.finish(f"已删除条目 #{item.recommendation_id}。")
    await recommend_command.finish(f"未知子命令：{action}")


def _validate_pool(pool: str) -> str:
    normalized = pool.lower()
    if normalized not in POOL_NAMES:
        raise ValueError("pool 必须是 activity、food 或 music")
    return normalized


def _friendly_recommendation(pool: str, content: str, *, nowdo: bool = False) -> str:
    if pool == "food":
        return f"要不今天吃这个：\n{content}"
    if pool == "music":
        return f"现在可以听听这首：\n{content}"
    if nowdo:
        return f"适合现在干的事情是：\n{content}"
    return f"不如现在去做这件事：\n{content}"


def _parse_add(tokens: list[str]) -> tuple[str, str, str, float, tuple[str, ...]]:
    if len(tokens) < 3:
        raise ValueError("用法：add <pool> <path> <content> [--weight n] [--tags a,b]")
    pool = _validate_pool(tokens[0])
    path = "" if tokens[1] in {"-", "root", "根"} else tokens[1]
    weight = 1.0
    tags: tuple[str, ...] = ()
    content_parts: list[str] = []
    index = 2
    while index < len(tokens):
        token = tokens[index]
        if token == "--weight":
            if index + 1 >= len(tokens):
                raise ValueError("--weight 缺少数值")
            weight = float(tokens[index + 1])
            index += 2
            continue
        if token == "--tags":
            if index + 1 >= len(tokens):
                raise ValueError("--tags 缺少内容")
            tags = tuple(item for item in tokens[index + 1].split(",") if item)
            index += 2
            continue
        content_parts.append(token)
        index += 1
    content = " ".join(content_parts).strip()
    if not content or weight <= 0:
        raise ValueError("内容不能为空且权重必须大于 0")
    return pool, path, content, weight, tags


async def _ensure_enabled(event, matcher) -> None:
    group_id = event_group_id(event)
    if group_id and not get_container().features.status("recommendation", group_id).enabled:
        await matcher.finish("当前群已关闭推荐功能。")
