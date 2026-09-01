from __future__ import annotations

import asyncio
import time

from amadeus_bot.bootstrap import build_container
from amadeus_bot.domain.ai import AITask


async def main() -> None:
    container = build_container()
    try:
        for task in (AITask.PROACTIVE_GATE, AITask.CHAT):
            started = time.perf_counter()
            result = await container.ai.complete(
                task,
                [
                    {"role": "system", "content": "Return only OK."},
                    {"role": "user", "content": "Connectivity probe."},
                ],
                user_id="probe",
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            print(
                f"task={task.value} provider={result.provider} model={result.model} "
                f"input_tokens={result.input_tokens} output_tokens={result.output_tokens} "
                f"latency_ms={elapsed_ms} nonempty={bool(result.content.strip())}"
            )
    finally:
        await container.close()


if __name__ == "__main__":
    asyncio.run(main())
