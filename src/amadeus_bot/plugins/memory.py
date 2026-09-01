from __future__ import annotations

import asyncio
import json
import re
from collections import Counter

from nonebot import on_command, on_message, on_regex
from nonebot.adapters.onebot.v11 import Message
from nonebot.log import logger
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.ai import AITask
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import event_group_id, finish_text_or_image
from amadeus_bot.services.analytics import AnalyticsService

command_registry.register(
    CommandSpec(
        name="memory",
        description="提交本人记忆处理申请；SUPERUSER 人工处理",
        usage=(
            "/memory request <view/edit/delete/optout> [说明]；"
            "/memory requests [pending/all]；/memory show <QQ> [memory_id]；"
            "/memory edit <QQ> <memory_id> <内容>；/memory delete <QQ> <memory_id>；"
            "/memory analysis <QQ> on/off"
        ),
        permission=PermissionLevel.EVERYONE,
        feature="memory",
        ai_callable=False,
        examples=(
            "/memory request view",
            "/memory request edit 我不再喜欢咖啡",
            "/memory request optout",
        ),
        notes=(
            "普通用户只能为本人提交处理申请；查看、编辑和删除由开发者人工处理",
            "optout 会立即关闭本人的新记忆候选提取，并创建处理申请",
            "requests/show/edit/delete/analysis 仅 SUPERUSER 可用，AI 无权处理",
            "长期记忆存放在 data/users/<QQ号>/user.sqlite3，跨群共享但不披露来源群原话",
        ),
    )
)

memory_command = on_command("memory", priority=10, block=True)
natural_request = on_regex(
    r"(?:查看|看看|修改|更改|删除|清除).{0,8}(?:我的)?记忆|退出(?:性格)?分析",
    priority=8,
    block=True,
)
memory_batch_listener = on_message(priority=90, block=False)
_message_counts: Counter[tuple[str, str]] = Counter()


@natural_request.handle()
async def handle_natural_request(event) -> None:
    text = event.get_plaintext().strip()
    request_type = _request_type(text)
    request_id = _create_request(event.get_user_id(), request_type, text)
    await natural_request.finish(
        f"已创建记忆处理申请 #{request_id}（{request_type}）。"
        "记忆内容不会直接向用户披露或自动修改，将由开发者人工处理。"
    )


@memory_command.handle()
async def handle_memory(event, arguments: Message = CommandArg()) -> None:
    tokens = arguments.extract_plain_text().split()
    is_superuser = get_container().permissions.role_for(event.get_user_id()) == PermissionLevel.SUPERUSER
    if not tokens:
        await memory_command.finish("用法：/memory request <view/edit/delete/optout> [说明]")
    if tokens[0] == "request":
        if len(tokens) < 2 or tokens[1] not in {"view", "edit", "delete", "optout"}:
            await memory_command.finish("申请类型必须是 view、edit、delete 或 optout。")
        request_id = _create_request(event.get_user_id(), tokens[1], " ".join(tokens[2:]))
        await memory_command.finish(f"已创建记忆处理申请 #{request_id}；开发者会人工处理。")
    if not is_superuser:
        await memory_command.finish("其余 memory 子命令仅 SUPERUSER 可用。")
    try:
        text = _execute_admin(tokens, event.get_user_id())
    except ValueError as exc:
        await memory_command.finish(f"参数错误：{exc}")
    await finish_text_or_image(memory_command, text, title="记忆管理", force_image=len(text) > 500)


@memory_batch_listener.handle()
async def handle_memory_batch(event) -> None:
    group_id = event_group_id(event)
    text = event.get_plaintext().strip()
    user_id = event.get_user_id()
    if not group_id or not text or text.startswith("/"):
        return
    container = get_container()
    if not container.features.status("memory", group_id).enabled:
        return
    if container.features.is_ignored(user_id, group_id, "ai") or not container.memory.analysis_enabled(
        user_id
    ):
        return
    key = (group_id, user_id)
    _message_counts[key] += 1
    if _message_counts[key] < 12:
        return
    _message_counts[key] = 0
    asyncio.create_task(_extract_memories(group_id, user_id))


async def _extract_memories(group_id: str, user_id: str) -> None:
    container = get_container()
    try:
        window = AnalyticsService(container.paths.logs).load_group(group_id, 24)
        rows = [row for row in window.records if str(row.get("user_id")) == user_id][-20:]
        evidence = [str(row.get("message_id", "")) for row in rows]
        transcript = "\n".join(str(row.get("plain_text", "")) for row in rows if row.get("plain_text"))
        if len(transcript) < 100:
            return
        prompt = (
            "从下列同一用户近期消息中只提取稳定、非敏感、将来有帮助的偏好或近况。"
            "不要提取身份凭据、联系方式、健康、财务、政治等敏感信息。"
            "输出严格 JSON 数组，每项含 category/content/confidence；没有则 []。\n\n" + transcript
        )
        response = await container.ai.complete(
            AITask.MEMORY_EXTRACTION,
            [{"role": "user", "content": prompt}],
            group_id=group_id,
            user_id=user_id,
        )
        candidates = _parse_json_array(response.content)
        for item in candidates[:3]:
            confidence = float(item.get("confidence", 0))
            if confidence < 0.75:
                continue
            container.memory.add_candidate(
                user_id,
                str(item.get("category", "preference")),
                str(item.get("content", "")),
                confidence=confidence,
                source_group_id=group_id,
                evidence_message_ids=tuple(evidence),
            )
    except Exception:
        logger.exception("批量记忆候选提取失败")


def _execute_admin(tokens: list[str], actor: str) -> str:
    repository = get_container().repository
    memory = get_container().memory
    action = tokens[0]
    if action == "requests":
        status = tokens[1] if len(tokens) > 1 else "pending"
        if status not in {"pending", "all"}:
            raise ValueError("状态必须是 pending 或 all")
        rows = repository.list_memory_requests(status)
        return (
            "\n".join(
                f"#{row['request_id']} user={row['user_id']} "
                f"type={row['request_type']} status={row['status']}"
                for row in rows
            )
            or "没有申请。"
        )
    if action == "show":
        if len(tokens) not in {2, 3} or not tokens[1].isdigit():
            raise ValueError("用法：/memory show <qq> [memory_id]")
        memory_id = int(tokens[2]) if len(tokens) == 3 and tokens[2].isdigit() else None
        rows = memory.list(tokens[1], memory_id)
        return (
            "\n".join(
                f"#{row.memory_id} [{row.category}] {row.content}\nconfidence={row.confidence:.2f} "
                f"sensitivity={row.sensitivity} version={row.version} "
                f"source_group={row.source_group_id or '-'}"
                for row in rows
            )
            or "没有记忆。"
        )
    if action == "edit":
        if len(tokens) < 4 or not tokens[1].isdigit() or not tokens[2].isdigit():
            raise ValueError("用法：/memory edit <qq> <memory_id> <content>")
        changed = memory.edit(tokens[1], int(tokens[2]), " ".join(tokens[3:]))
        repository.complete_memory_requests(tokens[1], actor)
        return "已修改并完成该用户的待处理申请。" if changed else "记忆不存在。"
    if action == "delete":
        if len(tokens) != 3 or not tokens[1].isdigit() or not tokens[2].isdigit():
            raise ValueError("用法：/memory delete <qq> <memory_id>")
        changed = memory.delete(tokens[1], int(tokens[2]))
        repository.complete_memory_requests(tokens[1], actor)
        return "已删除并完成该用户的待处理申请。" if changed else "记忆不存在。"
    if action == "analysis":
        if len(tokens) != 3 or not tokens[1].isdigit() or tokens[2] not in {"on", "off"}:
            raise ValueError("用法：/memory analysis <qq> on/off")
        memory.set_analysis(tokens[1], tokens[2] == "on")
        repository.complete_memory_requests(tokens[1], actor)
        return f"已将 {tokens[1]} 的性格分析设为 {tokens[2]}。"
    raise ValueError("管理员用法：requests/show/edit/delete/analysis")


def _create_request(user_id: str, request_type: str, detail: str) -> int:
    if request_type == "optout":
        get_container().memory.set_analysis(user_id, False)
    return get_container().repository.create_memory_request(user_id, request_type, detail)


def _request_type(text: str) -> str:
    if "退出" in text:
        return "optout"
    if "删除" in text or "清除" in text:
        return "delete"
    if "修改" in text or "更改" in text:
        return "edit"
    return "view"


def _parse_json_array(text: str) -> list[dict]:
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        return []
    value = json.loads(match.group(0))
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
