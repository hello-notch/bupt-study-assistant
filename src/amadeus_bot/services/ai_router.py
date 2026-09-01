from __future__ import annotations

import time
import tomllib
from pathlib import Path
from typing import Any

from amadeus_bot.adapters.ai_provider import (
    ApiCredential,
    OpenAICompatibleProvider,
    ProviderConfig,
)
from amadeus_bot.domain.ai import AIResponse, AITask, ModelTarget, TaskRoute
from amadeus_bot.repositories.core import CoreRepository


class AIRouteCatalog:
    def __init__(self, providers: dict[str, ProviderConfig], routes: dict[AITask, TaskRoute]) -> None:
        self.providers = providers
        self.routes = routes

    @classmethod
    def load(cls, path: Path) -> AIRouteCatalog:
        with path.open("rb") as stream:
            raw = tomllib.load(stream)
        providers = {
            name: ProviderConfig(
                name=name,
                credential_host=str(values["credential_host"]),
                api_prefix=str(values.get("api_prefix", "")),
            )
            for name, values in raw.get("providers", {}).items()
        }
        routes: dict[AITask, TaskRoute] = {}
        for task_name, values in raw.get("tasks", {}).items():
            task = AITask(task_name)
            routes[task] = TaskRoute(
                primary=ModelTarget.parse(str(values["primary"])),
                fallbacks=tuple(ModelTarget.parse(str(item)) for item in values.get("fallbacks", [])),
                temperature=float(values.get("temperature", 0.2)),
                max_tokens=int(values.get("max_tokens", 1000)),
            )
        missing = set(AITask) - routes.keys()
        if missing:
            names = ", ".join(sorted(item.value for item in missing))
            raise ValueError(f"AI 路由缺少任务：{names}")
        return cls(providers, routes)


class AIService:
    def __init__(
        self,
        catalog: AIRouteCatalog,
        credentials: dict[str, ApiCredential],
        repository: CoreRepository,
    ) -> None:
        self.catalog = catalog
        self.repository = repository
        self.providers: dict[str, OpenAICompatibleProvider] = {}
        for name, provider_config in catalog.providers.items():
            credential = credentials.get(provider_config.credential_host)
            if credential is not None:
                self.providers[name] = OpenAICompatibleProvider(provider_config, credential)

    def available(self) -> bool:
        return bool(self.providers)

    def route_description(self) -> dict[str, str]:
        return {
            task.value: f"{route.primary.provider}/{route.primary.model}"
            for task, route in self.catalog.routes.items()
        }

    async def complete(
        self,
        task: AITask,
        messages: list[dict[str, Any]],
        *,
        group_id: str | None = None,
        user_id: str | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AIResponse:
        quota = self.repository.ai_quota_for_task(task.value)
        if quota is not None and quota[1] >= quota[0]:
            raise AIQuotaExceeded(f"AI 任务 {task.value} 已达到当日调用上限 {quota[0]}")
        route = self.catalog.routes[task]
        errors: list[str] = []
        for target in (route.primary, *route.fallbacks):
            provider = self.providers.get(target.provider)
            if provider is None:
                errors.append(f"{target.provider}:credential-unavailable")
                continue
            started = time.perf_counter()
            try:
                result = await provider.complete(
                    model=target.model,
                    messages=messages,
                    temperature=route.temperature,
                    max_tokens=route.max_tokens,
                    tools=tools,
                )
            except Exception as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                error_type = type(exc).__name__
                self.repository.record_ai_usage(
                    task=task.value,
                    provider=target.provider,
                    model=target.model,
                    latency_ms=latency_ms,
                    success=False,
                    group_id=group_id,
                    user_id=user_id,
                    error_type=error_type,
                )
                errors.append(f"{target.provider}/{target.model}:{error_type}")
                continue
            latency_ms = int((time.perf_counter() - started) * 1000)
            self.repository.record_ai_usage(
                task=task.value,
                provider=result.provider,
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cached_tokens=result.cached_tokens,
                latency_ms=latency_ms,
                success=True,
                group_id=group_id,
                user_id=user_id,
            )
            return result
        raise RuntimeError("所有 AI 路由均不可用：" + "; ".join(errors))

    async def close(self) -> None:
        for provider in self.providers.values():
            await provider.close()


class AIQuotaExceeded(RuntimeError):
    pass
