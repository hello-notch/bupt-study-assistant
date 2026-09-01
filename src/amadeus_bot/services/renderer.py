from __future__ import annotations

import asyncio
import hashlib
import html
import re
from contextlib import suppress
from pathlib import Path


class RenderService:
    STYLE_VERSION = "amadeus-help-v1"

    def __init__(self, cache_dir: Path, *, max_concurrency: int = 2) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._playwright = None
        self._browser = None
        self._browser_lock = asyncio.Lock()

    def cache_key(self, content: str, *, kind: str, variant: str = "default") -> str:
        material = "\x1f".join((self.STYLE_VERSION, kind, variant, content))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    async def render_text(self, content: str, *, title: str = "Amadeus", variant: str = "default") -> Path:
        return await self._render(
            content,
            title=title,
            variant=variant,
            kind="plain-text",
            html_body=f"<pre>{html.escape(content)}</pre>",
        )

    async def render_markdown(
        self, content: str, *, title: str = "Amadeus", variant: str = "markdown"
    ) -> Path:
        from markdown_it import MarkdownIt

        if len(content) > 30_000:
            raise ValueError("Markdown 内容超过 30000 字符")
        renderer = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
        safe_markdown = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"[外链图片已阻止：\1]", content)
        rendered = renderer.render(safe_markdown)
        return await self._render(
            content,
            title=title,
            variant=variant,
            kind="markdown",
            html_body=f'<article class="markdown">{rendered}</article>',
        )

    async def _render(
        self,
        content: str,
        *,
        title: str,
        variant: str,
        kind: str,
        html_body: str,
    ) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        key = self.cache_key(content, kind=kind, variant=variant)
        output_path = self.cache_dir / f"{key}.png"
        if output_path.is_file() and output_path.stat().st_size > 0:
            return output_path
        async with self._semaphore:
            if output_path.is_file() and output_path.stat().st_size > 0:
                return output_path
            browser = await self._get_browser()
            page = await browser.new_page(
                viewport={"width": 980, "height": 800},
                device_scale_factor=2,
            )
            temporary = output_path.with_suffix(".tmp.png")
            try:
                await page.set_content(
                    self._build_html(html_body, title),
                    wait_until="load",
                    timeout=15_000,
                )
                await page.evaluate("document.fonts ? document.fonts.ready : Promise.resolve()")
                await page.locator(".card").screenshot(path=str(temporary))
                temporary.replace(output_path)
            finally:
                await page.close()
                if temporary.exists():
                    temporary.unlink(missing_ok=True)
            return output_path

    async def close(self) -> None:
        if self._browser is not None:
            # Ctrl+C may stop Playwright's child driver before NoneBot invokes
            # shutdown hooks.  A disconnected browser is already closed and
            # must not turn an otherwise clean Bot shutdown into a failure.
            with suppress(Exception):
                await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            with suppress(Exception):
                await self._playwright.stop()
            self._playwright = None

    async def _get_browser(self):
        if self._browser is not None:
            return self._browser
        async with self._browser_lock:
            if self._browser is not None:
                return self._browser
            try:
                from playwright.async_api import async_playwright
            except ModuleNotFoundError as exc:
                raise RuntimeError("缺少 Playwright，无法渲染帮助图片") from exc
            self._playwright = await async_playwright().start()
            try:
                self._browser = await self._playwright.chromium.launch(headless=True)
            except Exception as exc:
                await self._playwright.stop()
                self._playwright = None
                raise RuntimeError(
                    "无法启动 Playwright Chromium；请执行 playwright install chromium"
                ) from exc
            return self._browser

    @staticmethod
    def _build_html(body: str, title: str) -> str:
        safe_title = html.escape(title)
        return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
:root {{ color-scheme: light; font-family: "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 28px; background: #edf1f7; color: #202737; }}
.card {{ width: 900px; padding: 30px 34px; background: #fff; border: 1px solid #d8deea;
         border-radius: 18px; box-shadow: 0 12px 32px rgba(35, 48, 80, .10); }}
h1 {{ margin: 0 0 18px; color: #374b78; font-size: 30px; }}
pre {{ margin: 0; white-space: pre-wrap; overflow-wrap: anywhere;
       font: 19px/1.7 "Microsoft YaHei", "Noto Sans CJK SC", sans-serif; }}
.markdown {{ font-size: 18px; line-height: 1.7; overflow-wrap: anywhere; }}
.markdown h1,.markdown h2,.markdown h3 {{ color: #374b78; margin: 1em 0 .45em; }}
.markdown table {{ border-collapse: collapse; width: 100%; }}
.markdown th,.markdown td {{ border: 1px solid #ccd4e3; padding: 8px 10px; text-align: left; }}
.markdown code {{ background: #edf1f7; border-radius: 5px; padding: 2px 5px; }}
.markdown pre code {{ display: block; padding: 14px; white-space: pre-wrap; }}
.markdown img {{ max-width: 100%; }}
</style></head><body><main class="card"><h1>{safe_title}</h1>{body}</main></body></html>"""
