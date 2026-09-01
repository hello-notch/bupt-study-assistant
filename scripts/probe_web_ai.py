"""Probe the web assistant's configured chat model without printing secrets or content."""

from __future__ import annotations

import asyncio
import tomllib
from pathlib import Path

import httpx

from amadeus_bot.adapters.ai_provider import CredentialStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    routes = tomllib.loads((PROJECT_ROOT / "config/ai_routes.toml").read_text(encoding="utf-8"))
    primary = str(routes["tasks"]["chat"]["primary"])
    provider_name, model = primary.split("/", 1)
    provider = routes["providers"][provider_name]
    credential_host = str(provider["credential_host"])
    credential = CredentialStore.load(PROJECT_ROOT / "secrets/apikey.txt").get(credential_host)
    if credential is None:
        raise SystemExit("configured credential is unavailable")
    prefix = str(provider.get("api_prefix", "")).strip("/")
    endpoint = credential.base_url.rstrip("/") + (f"/{prefix}" if prefix else "") + "/chat/completions"
    headers = {"Authorization": f"Bearer {credential.api_key}"}
    async with httpx.AsyncClient(timeout=45, headers=headers) as client:
        response = await client.post(
            endpoint,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Return only OK."}],
                "max_tokens": 64,
                "thinking": {"type": "enabled"},
            },
        )
    nonempty = False
    if response.is_success:
        choices = response.json().get("choices") or []
        nonempty = bool(choices and (choices[0].get("message") or {}).get("content"))
    print(f"model={model} thinking_http={response.status_code} nonempty={nonempty}")
    response.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
