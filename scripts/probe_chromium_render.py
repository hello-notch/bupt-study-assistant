from __future__ import annotations

import asyncio
import time
from pathlib import Path

from amadeus_bot.services.renderer import RenderService

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def main() -> None:
    directory = PROJECT_ROOT / "data" / "cache" / "probe-chromium"
    renderer = RenderService(directory)
    try:
        output = await renderer.render_text(
            "Playwright Chromium cold-start verification",
            title="Chromium",
            variant=f"cold-start-{time.time_ns()}",
        )
        print(f"rendered={output.is_file()} bytes={output.stat().st_size}")
    finally:
        await renderer.close()


if __name__ == "__main__":
    asyncio.run(main())
