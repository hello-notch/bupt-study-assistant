from __future__ import annotations

import time

from nonebot import get_driver, on_command
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.params import CommandArg

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.ai import AITask
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import finish_text_or_image

for spec in (
    CommandSpec(
        name="health",
        description="查看机器人和依赖服务状态",
        usage="/health [detail | source <portal/activity/jwgl>]",
        permission=PermissionLevel.EVERYONE,
        ai_callable=True,
    ),
    CommandSpec(
        name="ai-cost",
        description="查看按任务/模型聚合的 AI 使用量",
        usage="/ai-cost [today/7d/30d]",
        permission=PermissionLevel.SUPERUSER,
        ai_callable=False,
    ),
    CommandSpec(
        name="ai-quota",
        description="查看或设置 AI 任务日调用配额",
        usage="/ai-quota status | set <purpose> <daily_limit>",
        permission=PermissionLevel.SUPERUSER,
        ai_callable=False,
    ),
):
    command_registry.register(spec)

health_command = on_command("health", priority=10, block=True)
cost_command = on_command("ai-cost", priority=5, block=True)
quota_command = on_command("ai-quota", priority=5, block=True)


@health_command.handle()
async def handle_health(bot: Bot, event, arguments: Message = CommandArg()) -> None:
    container = get_container()
    argument = arguments.extract_plain_text().strip()
    is_superuser = container.permissions.role_for(event.get_user_id()) == PermissionLevel.SUPERUSER
    if argument and not is_superuser:
        await health_command.finish("详细健康信息仅 SUPERUSER 可查看。")
    started = time.perf_counter()
    database_ok = container.database.fetch_one("SELECT 1 AS ok") is not None
    try:
        protocol_status = await bot.get_status()
        protocol_ok = bool(protocol_status.get("good", True)) if isinstance(protocol_status, dict) else True
    except Exception:
        protocol_ok = False
    if not argument:
        await health_command.finish(
            f"机器人：{'正常' if protocol_ok else '异常'}\n数据库：{'正常' if database_ok else '异常'}\n"
            f"AI：{'已配置' if container.ai.available() else '未配置'}"
        )
    if argument.startswith("source"):
        source = argument.removeprefix("source").strip()
        if source not in {"portal", "activity", "jwgl"}:
            await health_command.finish("数据源必须是 portal、activity 或 jwgl。")
        row = container.repository.get_source_health(source)
        if row is None:
            await health_command.finish(f"{source}：尚无抓取记录。")
        await health_command.finish(
            f"{source}\n最后成功：{row['last_success_at'] or '-'}\n"
            f"最后失败：{row['last_failure_at'] or '-'}\n"
            f"连续失败：{row['consecutive_failures']}\n缓存条目：{row['item_count']}\n"
            f"错误摘要：{row['error_summary'] or '-'}\ntrace：{row['trace_id'] or '-'}"
        )
    cache_count = sum(1 for _ in (container.paths.data / "cache" / "render").glob("*.png"))
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    routes = "\n".join(f"  {task}: {target}" for task, target in container.ai.route_description().items())
    text = (
        f"NapCat/OneBot：{'正常' if protocol_ok else '异常'}\n"
        f"数据库：{'正常' if database_ok else '异常'}\n"
        f"AI provider：{len(container.ai.providers)}\n"
        f"渲染缓存：{cache_count} 张\n诊断耗时：{elapsed_ms} ms\nAI 路由：\n{routes}"
    )
    await finish_text_or_image(health_command, text, title="Amadeus 健康状态")


@cost_command.handle()
async def handle_cost(event, arguments: Message = CommandArg()) -> None:
    if get_container().permissions.role_for(event.get_user_id()) != PermissionLevel.SUPERUSER:
        await cost_command.finish("该命令仅 SUPERUSER 可用。")
    period = arguments.extract_plain_text().strip() or "today"
    days = {"today": 1, "7d": 7, "30d": 30}.get(period)
    if days is None:
        await cost_command.finish("用法：/ai-cost [today/7d/30d]")
    rows = get_container().repository.ai_usage_summary(days)
    if not rows:
        await cost_command.finish("指定时间内没有 AI 调用记录。")
    lines = [f"AI 使用量 · {period}", "价格未配置，因此暂不显示不可靠的费用估算。", ""]
    for row in rows:
        lines.append(
            f"{row['provider']}/{row['model']} · {row['task']}\n"
            f"  calls={row['calls']} in={row['input_tokens']} out={row['output_tokens']} "
            f"avg={row['avg_latency_ms']}ms failures={row['failures']}"
        )
    await finish_text_or_image(cost_command, "\n".join(lines), title="AI 成本与用量", force_image=True)


@quota_command.handle()
async def handle_quota(event, arguments: Message = CommandArg()) -> None:
    container = get_container()
    if container.permissions.role_for(event.get_user_id()) != PermissionLevel.SUPERUSER:
        await quota_command.finish("该命令仅 SUPERUSER 可用。")
    tokens = arguments.extract_plain_text().split()
    if not tokens or tokens[0] == "status":
        rows = container.repository.ai_quota_status()
        text = (
            "\n".join(f"{row['task']}: {row['used_today']}/{row['daily_limit']} calls" for row in rows)
            or "尚未设置任务配额。"
        )
        await quota_command.finish(text)
    if len(tokens) == 3 and tokens[0] == "set" and tokens[2].isdigit():
        try:
            task = AITask(tokens[1])
        except ValueError:
            await quota_command.finish("未知任务，可用值：" + "、".join(item.value for item in AITask))
        container.repository.set_ai_quota(task.value, int(tokens[2]), event.get_user_id())
        await quota_command.finish(f"已设置 {task.value} 的日调用上限为 {int(tokens[2])}。")
    await quota_command.finish("用法：/ai-quota status | set <purpose> <daily_limit>")


@get_driver().on_shutdown
async def close_services() -> None:
    await get_container().close()
