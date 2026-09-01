"""Inspect the public portal login frame without reading or submitting credentials."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

PORTAL_URL = "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154"


def safe_url(value: str) -> str:
    parts = urlsplit(value)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


async def main() -> None:
    responses: list[dict[str, object]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        try:
            context = await browser.new_context()
            page = await context.new_page()

            def record_response(response: object) -> None:
                url = str(getattr(response, "url", ""))
                if "auth.bupt.edu.cn" in url:
                    responses.append(
                        {
                            "status": getattr(response, "status", None),
                            "url": safe_url(url),
                        }
                    )

            page.on("response", record_response)
            await page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(3_000)
            initial_cookie_names = sorted({cookie["name"] for cookie in await context.cookies()})
            login_ui: dict[str, object] = {}
            if await page.locator("#loginIframe").count():
                login_frame = page.frame_locator("#loginIframe")
                login_links = login_frame.locator('a[href="javascript:;"]')
                login_ui["links"] = [
                    {
                        "text": " ".join(((await login_links.nth(index).text_content()) or "").split()),
                        "class": await login_links.nth(index).get_attribute("class"),
                    }
                    for index in range(await login_links.count())
                ]
                if await login_links.count() >= 2:
                    await login_links.nth(1).click()
                    await page.wait_for_timeout(500)
                login_ui["username_visible"] = await login_frame.locator("#username").is_visible()
            frames = []
            for frame in page.frames:
                body = await frame.locator("body").inner_text(timeout=5_000)
                frames.append(
                    {
                        "url": safe_url(frame.url),
                        "body_preview": " ".join(body.split())[:300],
                        "username_count": await frame.locator("#username").count(),
                    }
                )
            print(
                json.dumps(
                    {
                        "page_url": safe_url(page.url),
                        "cookie_names": initial_cookie_names,
                        "login_ui": login_ui,
                        "responses": responses,
                        "frames": frames,
                    },
                    ensure_ascii=True,
                    indent=2,
                )
            )
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
