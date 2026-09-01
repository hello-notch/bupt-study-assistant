from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from amadeus_bot.domain.ai import AIResponse, ToolCall


@dataclass(frozen=True, slots=True)
class ApiCredential:
    base_url: str
    api_key: str

    @property
    def host(self) -> str:
        return httpx.URL(self.base_url).host


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    name: str
    credential_host: str
    api_prefix: str


class CredentialStore:
    @staticmethod
    def load(path: Path) -> dict[str, ApiCredential]:
        if not path.is_file():
            return {}
        credentials: dict[str, ApiCredential] = {}
        pending_key: str | None = None
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r"^([^:=]+)\s*[:=]\s*(.*)$", line)
            if match is None:
                continue
            normalized_label = match.group(1).strip().lower()
            value = match.group(2).strip()
            if normalized_label == "apikey":
                pending_key = value
            elif normalized_label == "url" and pending_key:
                credential = ApiCredential(base_url=value.rstrip("/"), api_key=pending_key)
                credentials[credential.host] = credential
                pending_key = None
        return credentials


class OpenAICompatibleProvider:
    def __init__(
        self,
        config: ProviderConfig,
        credential: ApiCredential,
        *,
        timeout_seconds: float = 45.0,
    ) -> None:
        self.config = config
        self.credential = credential
        prefix = config.api_prefix.strip()
        self.api_base = credential.base_url.rstrip("/") + ("/" + prefix.strip("/") if prefix else "")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Authorization": f"Bearer {credential.api_key}"},
        )

    async def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
    ) -> AIResponse:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        response = await self._client.post(f"{self.api_base}/chat/completions", json=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"AI provider {self.config.name} returned HTTP {response.status_code}")
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"AI provider {self.config.name} returned no choices")
        message = choices[0].get("message") or {}
        # reasoning_content is internal model reasoning and must not be shown to QQ users.
        content = message.get("content") or ""
        tool_calls = tuple(_parse_tool_call(item) for item in message.get("tool_calls") or [])
        usage = data.get("usage") or {}
        prompt_details = usage.get("prompt_tokens_details") or {}
        return AIResponse(
            content=str(content),
            provider=self.config.name,
            model=model,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cached_tokens=int(prompt_details.get("cached_tokens") or 0),
            raw_usage=usage,
            tool_calls=tool_calls,
        )

    async def close(self) -> None:
        await self._client.aclose()


def _parse_tool_call(raw: dict[str, Any]) -> ToolCall:
    function = raw.get("function") or {}
    arguments_raw = function.get("arguments") or "{}"
    if isinstance(arguments_raw, str):
        try:
            arguments = json.loads(arguments_raw)
        except json.JSONDecodeError:
            arguments = {}
    elif isinstance(arguments_raw, dict):
        arguments = arguments_raw
    else:
        arguments = {}
    return ToolCall(
        call_id=str(raw.get("id") or ""),
        name=str(function.get("name") or ""),
        arguments=arguments,
    )
