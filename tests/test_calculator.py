import math

import pytest

from amadeus_bot.services.calculator import CalculationError, calculate, format_result


def test_calculate_allowed_expression() -> None:
    assert calculate("sqrt(9) + 2 ** 3") == 11
    assert calculate("sin(pi / 2)") == pytest.approx(1.0)


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('whoami')",
        "(1).__class__",
        "[1, 2, 3]",
        "2 ** 101",
        "'text'",
    ],
)
def test_calculate_rejects_unsafe_or_excessive_expression(expression: str) -> None:
    with pytest.raises(CalculationError):
        calculate(expression)


def test_calculate_constants() -> None:
    assert calculate("tau") == math.tau


def test_calculate_common_scientific_notation() -> None:
    assert calculate("ln(e)") == pytest.approx(1.0)
    assert calculate("lg(1000)") == pytest.approx(3.0)
    assert calculate("tan7") == pytest.approx(math.tan(7))
    assert calculate("2^8") == 256
    assert calculate("sqrt(8, 3)") == pytest.approx(2.0)
    assert calculate("i^2") == pytest.approx(-1.0)


def test_format_result_keeps_at_most_eight_decimal_places() -> None:
    assert format_result(1 / 3) == "0.33333333"
    assert format_result(2.0) == "2"
    assert format_result(1 + 2j) == "1+2i"
