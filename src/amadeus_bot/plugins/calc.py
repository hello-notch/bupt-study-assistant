from __future__ import annotations

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg

from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.services.calculator import CalculationError, calculate, format_result

command_registry.register(
    CommandSpec(
        name="calc",
        description="安全计算数学表达式",
        usage="/calc <expression>",
        permission=PermissionLevel.EVERYONE,
        ai_callable=True,
        examples=(
            "/calc sqrt(2) * 10",
            "/calc sin(pi / 2)",
            "/calc sqrt(5)*sin(pi/e)-ln(tan7)",
            "/calc 2^8 + lg(100)",
        ),
        notes=(
            "三角函数使用弧度制",
            "支持 pi、e、tau、i，支持 ln/log、lg/log10 和反三角函数",
            "结果最多保留 8 位小数并去掉末尾无意义的 0",
        ),
    )
)

calc_command = on_command("calc", priority=10, block=True)


@calc_command.handle()
async def handle_calc(arguments: Message = CommandArg()) -> None:
    expression = arguments.extract_plain_text().strip()
    if not expression:
        await calc_command.finish("用法：/calc <expression>")
    try:
        result = calculate(expression)
    except CalculationError as exc:
        await calc_command.finish(f"计算失败：{exc}")
    await calc_command.finish(f"{expression} = {format_result(result)}")
