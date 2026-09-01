from __future__ import annotations

import ast
import cmath
import math
import operator
import re
from collections.abc import Callable


class CalculationError(ValueError):
    pass


Number = int | float | complex


def _safe_sqrt(value: Number, degree: Number = 2) -> Number:
    if degree == 0:
        raise ValueError("根指数不能为 0")
    if isinstance(value, (int, float)) and value >= 0 and isinstance(degree, (int, float)):
        return value ** (1 / degree)
    return complex(value) ** (1 / degree)


_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Number, Number], Number]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Number], Number]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_FUNCTIONS: dict[str, Callable[..., Number]] = {
    "abs": abs,
    "sqrt": _safe_sqrt,
    "sin": cmath.sin,
    "cos": cmath.cos,
    "tan": cmath.tan,
    "asin": cmath.asin,
    "acos": cmath.acos,
    "atan": cmath.atan,
    "arcsin": cmath.asin,
    "arccos": cmath.acos,
    "arctan": cmath.atan,
    "ln": cmath.log,
    "log": cmath.log,
    "lg": cmath.log10,
    "log10": cmath.log10,
    "exp": cmath.exp,
    "round": round,
}
_CONSTANTS: dict[str, Number] = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
    "i": 1j,
    "j": 1j,
}
_IMPLICIT_FUNCTIONS = tuple(sorted((name for name in _FUNCTIONS if name != "round"), key=len, reverse=True))


def calculate(expression: str) -> Number:
    normalized = normalize_expression(expression)
    if not normalized or len(normalized) > 200:
        raise CalculationError("表达式长度必须为 1～200 个字符")
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError as exc:
        raise CalculationError(f"语法错误，位置 {exc.offset or 0}") from exc
    if sum(1 for _ in ast.walk(tree)) > 80:
        raise CalculationError("表达式过于复杂")
    result = _evaluate(tree.body)
    if not _is_finite(result):
        raise CalculationError("结果不是有限数")
    return _real_if_close(result)


def normalize_expression(expression: str) -> str:
    text = expression.strip().replace("[", "(").replace("]", ")")
    text = text.replace("{", "(").replace("}", ")").replace("^", "**")
    # Accept the common shorthand tan7 / sinpi while keeping normal function
    # calls unchanged. Only a single numeric or named constant is expanded.
    function_pattern = "|".join(map(re.escape, _IMPLICIT_FUNCTIONS))
    argument_pattern = r"-?(?:\d+(?:\.\d+)?|pi|tau|e|i|j)"
    text = re.sub(
        rf"(?<![A-Za-z0-9_])({function_pattern})\s*({argument_pattern})(?![A-Za-z0-9_])",
        r"\1(\2)",
        text,
    )
    # Python writes imaginary values as j; accept the mathematical i notation,
    # including 2i, without enabling arbitrary names.
    text = re.sub(r"(?<=\d)i\b", "j", text)
    return text


def format_result(value: Number, *, decimal_places: int = 8) -> str:
    value = _real_if_close(value)
    if isinstance(value, complex):
        real = _format_real(value.real, decimal_places)
        imaginary = _format_real(abs(value.imag), decimal_places)
        if abs(value.real) < 1e-12:
            coefficient = _format_real(value.imag, decimal_places)
            return "i" if coefficient == "1" else "-i" if coefficient == "-1" else f"{coefficient}i"
        sign = "+" if value.imag >= 0 else "-"
        coefficient = "" if imaginary == "1" else imaginary
        return f"{real}{sign}{coefficient}i"
    return _format_real(float(value), decimal_places)


def _evaluate(node: ast.AST) -> Number:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float, complex)):
            raise CalculationError("只允许数字常量")
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise CalculationError(f"不允许的名称：{node.id}")
    if isinstance(node, ast.BinOp):
        function = _BINARY_OPERATORS.get(type(node.op))
        if function is None:
            raise CalculationError("不允许的运算符")
        left = _evaluate(node.left)
        right = _evaluate(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise CalculationError("指数绝对值不能超过 100")
        try:
            result = function(left, right)
        except (ArithmeticError, OverflowError, TypeError, ValueError) as exc:
            raise CalculationError(str(exc)) from exc
        if abs(result) > 1e100:
            raise CalculationError("结果绝对值过大")
        return result
    if isinstance(node, ast.UnaryOp):
        function = _UNARY_OPERATORS.get(type(node.op))
        if function is None:
            raise CalculationError("不允许的一元运算符")
        return function(_evaluate(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise CalculationError("只允许白名单数学函数")
        if node.keywords:
            raise CalculationError("函数不接受关键字参数")
        arguments = [_evaluate(argument) for argument in node.args]
        try:
            return _FUNCTIONS[node.func.id](*arguments)
        except (ArithmeticError, OverflowError, TypeError, ValueError) as exc:
            raise CalculationError(str(exc)) from exc
    raise CalculationError(f"不允许的语法：{type(node).__name__}")


def _real_if_close(value: Number) -> Number:
    if isinstance(value, complex) and abs(value.imag) < 1e-12:
        return value.real
    return value


def _is_finite(value: Number) -> bool:
    if isinstance(value, complex):
        return math.isfinite(value.real) and math.isfinite(value.imag)
    return math.isfinite(float(value))


def _format_real(value: float, decimal_places: int) -> str:
    if abs(value) < 10 ** (-(decimal_places + 1)):
        value = 0.0
    if value and (abs(value) < 10 ** (-decimal_places) or abs(value) >= 1e12):
        return f"{value:.{decimal_places}g}"
    return f"{value:.{decimal_places}f}".rstrip("0").rstrip(".") or "0"
