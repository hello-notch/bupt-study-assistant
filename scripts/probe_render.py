from __future__ import annotations

import asyncio

from amadeus_bot.bootstrap import build_container


async def main() -> None:
    container = build_container()
    try:
        content = "Amadeus 帮助图片缓存测试 v2\n/help [command]\n/干什么\n/吃什么\n/推歌（/听什么）"
        first = await container.renderer.render_text(content, title="Amadeus Bot 帮助", variant="probe-v2")
        second = await container.renderer.render_text(content, title="Amadeus Bot 帮助", variant="probe-v2")
        print(f"rendered={first.is_file()} bytes={first.stat().st_size} cache_hit={first == second}")
    finally:
        await container.close()


if __name__ == "__main__":
    asyncio.run(main())
