from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AITask(StrEnum):
    CHAT = "chat"
    TOOL_PLANNER = "tool_planner"
    PROACTIVE_GATE = "proactive_gate"
    SUMMARY = "summary"
    STATS_ANALYSIS = "stats_analysis"
    MEMORY_EXTRACTION = "memory_extraction"
    VISION = "vision"
    COMPLEX_REASONING = "complex_reasoning"


@dataclass(frozen=True, slots=True)
class ModelTarget:
    provider: str
    model: str

    @classmethod
    def parse(cls, value: str) -> ModelTarget:
        provider, separator, model = value.partition("/")
        if not separator or not provider or not model:
            raise ValueError(f"无效模型目标：{value!r}")
        return cls(provider=provider, model=model)


@dataclass(frozen=True, slots=True)
class TaskRoute:
    primary: ModelTarget
    fallbacks: tuple[ModelTarget, ...] = ()
    temperature: float = 0.2
    max_tokens: int = 1000


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AIResponse:
    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    raw_usage: dict[str, Any] = field(default_factory=dict)
    tool_calls: tuple[ToolCall, ...] = ()
