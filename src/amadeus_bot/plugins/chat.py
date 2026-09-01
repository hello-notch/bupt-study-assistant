from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.params import CommandArg
from nonebot.rule import to_me

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.ai import AITask
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import event_group_id, finish_text_or_image, reply_message_id
from amadeus_bot.services.tools import ToolExecutionContext

command_registry.register(
    CommandSpec(
        name="chat",
        description="与 Amadeus 进行角色化对话",
        usage="/chat <message>；也可 @ 或回复机器人",
        permission=PermissionLevel.EVERYONE,
        feature="chat",
        ai_callable=False,
    )
)
command_registry.register(
    CommandSpec(
        name="history",
        description="查看当前会话下一次交给模型的系统提示与最近上下文",
        usage="/history [1-30]",
        permission=PermissionLevel.EVERYONE,
        feature="chat",
        ai_callable=False,
        examples=("/history", "/history 20"),
        notes=("群聊只展示当前群的 AI 对话上下文；私聊只展示本人的私聊上下文",),
    )
)

chat_command = on_command("chat", priority=10, block=True)
history_command = on_command("history", priority=10, block=True)
mention_matcher = on_message(rule=to_me(), priority=20, block=True)
proactive_matcher = on_message(priority=80, block=False)
_proactive_times: defaultdict[str, deque[float]] = defaultdict(deque)
_last_seen: dict[str, float] = {}


@chat_command.handle()
async def handle_chat(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    text = arguments.extract_plain_text().strip()
    if not text:
        await chat_command.finish("用法：/chat <message>")
    await _respond(chat_command, bot, event, text)


@history_command.handle()
async def handle_history(event, arguments: Message = CommandArg()) -> None:
    text = arguments.extract_plain_text().strip()
    if text and (not text.isdigit() or not 1 <= int(text) <= 30):
        await history_command.finish("用法：/history [1-30]")
    limit = int(text or "14")
    user_id = event.get_user_id()
    group_id = event_group_id(event)
    scope_key = f"group:{group_id}" if group_id else f"private:{user_id}"
    rows = get_container().repository.recent_conversation(scope_key, limit=limit)
    lines = [
        "模型当前上下文",
        f"作用域：{'群 ' + group_id if group_id else '私聊 ' + user_id}",
        f"聊天主模型：{get_container().ai.route_description()['chat']}",
        f"正常回复默认读取最近 14 条；本次展示 {limit} 条。",
        "",
        "【系统提示】",
        _load_persona().strip() or "（未配置）",
        "",
        "【最近对话】",
    ]
    if rows:
        for index, row in enumerate(rows, start=1):
            role = "用户" if row["role"] == "user" else "Amadeus"
            lines.append(f"{index}. {role}\n{row['content']}")
    else:
        lines.append("（当前作用域还没有 AI 对话记录）")
    await finish_text_or_image(
        history_command,
        "\n\n".join(lines),
        title="模型上下文",
        force_image=True,
        variant=f"history:{scope_key}:{limit}",
    )


@mention_matcher.handle()
async def handle_mention(bot: Bot, event) -> None:
    text = event.get_plaintext().strip()
    if not text or text.startswith("/"):
        return
    await _respond(mention_matcher, bot, event, text)


@proactive_matcher.handle()
async def handle_proactive(bot: Bot, event) -> None:
    group_id = event_group_id(event)
    text = event.get_plaintext().strip()
    if not group_id or not text or text.startswith("/"):
        return
    container = get_container()
    if not container.features.status("proactive_chat", group_id).enabled:
        return
    if container.features.is_ignored(event.get_user_id(), group_id, "ai"):
        return
    now = time.monotonic()
    times = _proactive_times[group_id]
    while times and times[0] < now - 600:
        times.popleft()
    if len(times) >= 2 or (times and now - times[-1] < 60):
        return
    score = _proactive_score(text, group_id, now)
    if score < 2:
        return
    await asyncio.sleep(2.0)
    should_respond = score >= 4
    if not should_respond:
        try:
            gate = await container.ai.complete(
                AITask.PROACTIVE_GATE,
                [
                    {
                        "role": "user",
                        "content": (
                            "判断 Amadeus 是否应主动接话。只回复 JSON："
                            '{"respond":true/false,"confidence":0-1,"reason":"..."}。消息：' + text
                        ),
                    }
                ],
                group_id=group_id,
                user_id=event.get_user_id(),
            )
            decision = json.loads(re.search(r"\{[\s\S]*\}", gate.content).group(0))
            should_respond = bool(decision.get("respond")) and float(decision.get("confidence", 0)) >= 0.7
        except Exception:
            return
    if not should_respond:
        return
    times.append(time.monotonic())
    await _respond(proactive_matcher, bot, event, text)


async def _respond(matcher, bot: Bot, event, text: str) -> None:
    container = get_container()
    group_id = event_group_id(event)
    if group_id and not container.features.status("chat", group_id).enabled:
        await matcher.finish("当前群已关闭聊天功能。")
    user_id = event.get_user_id()
    if container.features.is_ignored(user_id, group_id, "ai"):
        return
    await container.activity_log.record(
        "ai_reply",
        f"Bot 选择回复消息 #{getattr(event, 'message_id', '-')}: {text[:1000]}",
        status="started",
        user_id=user_id,
        group_id=group_id,
        message_id=str(getattr(event, "message_id", "") or "") or None,
    )
    scope_key = f"group:{group_id}" if group_id else f"private:{user_id}"
    enriched = await _enrich_input(container, bot, event, text, group_id, user_id)
    stored_content = f"[{user_id}]: {enriched}" if group_id else enriched
    container.repository.append_conversation(scope_key, "user", stored_content, user_id)
    messages = [{"role": "system", "content": _load_persona()}]
    messages.extend(container.repository.recent_conversation(scope_key, limit=14))
    try:
        response = await container.ai.complete(
            AITask.CHAT,
            messages,
            group_id=group_id,
            user_id=user_id,
            tools=container.ai_tools.schemas(),
        )
        response = await _resolve_tool_calls(
            container,
            response,
            messages,
            user_id=user_id,
            group_id=group_id,
            bot=bot,
            replied_message_id=reply_message_id(event),
        )
    except Exception:
        await matcher.finish("Amadeus 暂时无法连接到 AI 服务，请稍后再试。")
    reply = response.content.strip()
    if not reply:
        await matcher.finish("AI 返回了空内容，请稍后重试。")
    container.repository.append_conversation(scope_key, "assistant", reply, None)
    await container.activity_log.record(
        "ai_reply",
        f"AI 生成回复，模型={response.provider}/{response.model}：{reply[:1600]}",
        user_id=user_id,
        group_id=group_id,
        message_id=str(getattr(event, "message_id", "") or "") or None,
        details={
            "provider": response.provider,
            "model": response.model,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        },
    )
    await finish_text_or_image(matcher, reply, title="Amadeus")


async def _resolve_tool_calls(
    container,
    response,
    messages,
    *,
    user_id: str,
    group_id: str | None,
    bot: Bot,
    replied_message_id: str | None,
):
    context = ToolExecutionContext.for_requester(
        user_id, group_id, bot=bot, replied_message_id=replied_message_id
    )
    for _ in range(2):
        if not response.tool_calls:
            return response
        assistant_tool_calls = []
        for call in response.tool_calls[:3]:
            assistant_tool_calls.append(
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
            )
        messages.append(
            {
                "role": "assistant",
                "content": response.content or None,
                "tool_calls": assistant_tool_calls,
            }
        )
        for call in response.tool_calls[:3]:
            result = await container.ai_tools.execute(call.name, call.arguments, context)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.call_id,
                    "content": result,
                }
            )
            trace_id = uuid.uuid4().hex
            container.repository.record_audit(
                trace_id,
                f"ai_tool.{call.name}",
                user_id,
                "success" if '"success": true' in result else "rejected",
                subject_user_id=user_id,
                group_id=group_id,
                parameter_summary="AI tool invocation; arguments omitted",
            )
        response = await container.ai.complete(
            AITask.CHAT,
            messages,
            group_id=group_id,
            user_id=user_id,
            tools=container.ai_tools.schemas(),
        )
    if response.tool_calls:
        raise RuntimeError("AI 工具调用轮数超过限制")
    return response


def _load_persona() -> str:
    persona_dir = Path(__file__).resolve().parents[1] / "persona"
    parts = []
    for name in ("canon.md", "style.md", "runtime.md"):
        path = persona_dir / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)


async def _enrich_input(container, bot: Bot, event, text: str, group_id: str | None, user_id: str) -> str:
    additions: list[str] = []
    for segment in event.get_message():
        if segment.type == "image" and segment.data.get("url"):
            url = str(segment.data["url"])
            digest = hashlib.sha256(url.encode()).hexdigest()
            description = container.repository.get_media_description(digest)
            if description is None:
                try:
                    result = await container.ai.complete(
                        AITask.VISION,
                        [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": "简洁描述这张图片或表情的可见内容和情绪，不猜测身份。",
                                    },
                                    {"type": "image_url", "image_url": {"url": url}},
                                ],
                            }
                        ],
                        group_id=group_id,
                        user_id=user_id,
                    )
                    description = result.content.strip()
                    container.repository.save_media_description(digest, "image", description, result.model)
                except Exception:
                    description = "[图片，视觉服务暂不可用]"
            additions.append("图片描述：" + description)
        elif segment.type == "record":
            try:
                result = await bot.call_api("fetch_ptt_text", file=segment.data.get("file"))
                transcript = result.get("text") if isinstance(result, dict) else str(result)
            except Exception:
                transcript = "语音转写失败"
            additions.append("语音内容：" + transcript)
    urls = re.findall(r"https?://\S+", text)
    if urls:
        additions.append("消息包含链接（未自动访问）：" + " ".join(urls[:3]))
    return text + (("\n" + "\n".join(additions)) if additions else "")


def _proactive_score(text: str, group_id: str, now: float) -> int:
    score = 0
    lowered = text.lower()
    if any(name in lowered for name in ("amadeus", "阿玛迪斯", "助手", "机器人")):
        score += 4
    if text.endswith(("?", "？")):
        score += 2
    if any(word in text for word in ("有人知道", "怎么", "为什么", "求推荐", "怎么办")):
        score += 1
    previous = _last_seen.get(group_id)
    if previous and now - previous < 3:
        score -= 1
    _last_seen[group_id] = now
    return score
