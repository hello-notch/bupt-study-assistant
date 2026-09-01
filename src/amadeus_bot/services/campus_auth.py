from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
from playwright.async_api import BrowserContext, Page, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PORTAL_LIST_URL = "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154"
JWGL_LOGIN_URL = "https://jwgl.bupt.edu.cn/jsxsd/"
JWGL_HOME_URL = "https://jwgl.bupt.edu.cn/jsxsd/framework/xsMain_bjyddx.jsp"
ACTIVITY_BASE_URL = "https://dekt.bupt.edu.cn"
ACTIVITY_LOGIN_PATH = "/api/v1/auth/sessions"


class CampusSessionExpired(RuntimeError):
    pass


class CampusAuthenticator:
    def __init__(self) -> None:
        self.password_file = _resolve_project_path(
            os.getenv("AMADEUS_PASSWORD_FILE", "secrets/campus-password.txt")
        )

    @property
    def available(self) -> bool:
        return self.password_file.is_file()

    async def login_portal(self) -> None:
        account, password = self._load_credentials()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self._portal_headless(),
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(PORTAL_LIST_URL, wait_until="domcontentloaded", timeout=30_000)
                if "auth.bupt.edu.cn/authserver/login" not in page.url:
                    await self._save_cookie_header(context, PORTAL_LIST_URL, "portal")
                    return
                await self._submit_portal_login(page, account, password)
                if not re.match(r"^https?://my\.bupt\.edu\.cn/", page.url):
                    raise RuntimeError(f"信息门户自动登录未成功；当前页面 {page.url}")
                await page.goto(PORTAL_LIST_URL, wait_until="domcontentloaded", timeout=30_000)
                if "auth.bupt.edu.cn/authserver/login" in page.url:
                    raise RuntimeError("信息门户自动登录后仍返回统一认证页")
                await self._save_cookie_header(context, PORTAL_LIST_URL, "portal")
            finally:
                await browser.close()

    @staticmethod
    async def _submit_portal_login(page: Page, account: str, password: str) -> None:
        """Submit the current BUPT CAS login UI.

        The public page keeps an old hidden form in its top document, while the
        actual login controls live in ``#loginIframe``.  Prefer the real UI and
        retain the hidden form only as a compatibility fallback.
        """
        if await page.locator("#loginIframe").count():
            frame = page.frame_locator("#loginIframe")
            # The iframe response is occasionally decoded with the wrong
            # charset in headless Chromium, so avoid Chinese text selectors.
            login_tabs = frame.locator('a[href="javascript:;"]')
            await login_tabs.nth(1).wait_for(state="visible", timeout=15_000)
            await login_tabs.nth(1).click()

            username = frame.locator("#username")
            password_box = frame.locator("#password")
            await username.wait_for(state="visible", timeout=15_000)
            await username.fill(account)
            await password_box.fill(password)
            captcha = frame.locator("#cptValue")
            if await captcha.is_visible():
                raise RuntimeError("信息门户本次登录要求图形验证码，无法自动续登")
            await frame.locator("input.submit-btn:visible").first.click()
        else:
            username = page.locator('input[name="username"]')
            password_box = page.locator('input[name="password"]')
            if not await username.is_visible():
                await page.locator("#default").evaluate("element => { element.style.display = 'block'; }")
            await username.wait_for(state="visible", timeout=15_000)
            await username.fill(account)
            await password_box.fill(password)
            await page.locator('input[type="submit"]').click()

        try:
            await page.wait_for_url(
                re.compile(r"^https?://my\.bupt\.edu\.cn/"),
                wait_until="domcontentloaded",
                timeout=30_000,
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("信息门户登录表单提交后没有进入信息门户") from exc

    async def login_jwgl(self) -> None:
        account, password = self._load_credentials()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self._headless())
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(JWGL_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
                await page.locator('input[name="userAccount"]').fill(account)
                await page.locator('input[name="userPassword"]').fill(password)
                await page.get_by_role("button", name="登 录").click()
                await page.wait_for_url(re.compile(r"/jsxsd/framework/"), timeout=30_000)
                await page.goto(JWGL_HOME_URL, wait_until="domcontentloaded", timeout=30_000)
                if await _looks_like_jwgl_login(page):
                    raise RuntimeError("教务系统自动登录后仍返回登录页")
                await self._save_cookie_header(context, JWGL_HOME_URL, "jwgl")
            finally:
                await browser.close()

    async def login_activity(self) -> None:
        """Refresh the Second Classroom JWT with the site's student login API."""
        account, password = self._load_credentials()
        async with httpx.AsyncClient(base_url=ACTIVITY_BASE_URL, timeout=20.0) as client:
            response = await client.post(
                ACTIVITY_LOGIN_PATH,
                data={
                    "username": account,
                    "password": password,
                    "code": "",
                    "captcha": "",
                },
            )

        real_status = _real_response_status(response)
        if real_status in {419, 420}:
            token = await self._login_activity_browser(account, password)
        else:
            if real_status in {401, 403}:
                raise RuntimeError("第二课堂自动登录失败，请检查学工号和密码")
            if real_status >= 400:
                raise RuntimeError(f"第二课堂自动登录失败（HTTP {real_status}）")
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError("第二课堂登录响应不是 JSON") from exc
            token = payload.get("data") if isinstance(payload, dict) else None
        if not _looks_like_jwt(token):
            raise RuntimeError("第二课堂登录响应未包含有效 token")

        path = _resolve_project_path(os.getenv("AMADEUS_ACTIVITY_TOKEN_FILE", "secrets/activity-token.txt"))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(token, encoding="utf-8")
        temporary.replace(path)

    async def _login_activity_browser(self, account: str, password: str) -> str:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=self._activity_headless(),
                args=["--disable-blink-features=AutomationControlled"],
                ignore_default_args=["--enable-automation"],
            )
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(ACTIVITY_BASE_URL, wait_until="domcontentloaded", timeout=30_000)
                await page.locator('input[placeholder="学工号"]').fill(account)
                await page.locator('input[placeholder="密码"]').fill(password)
                await page.get_by_role("button", name="登录").click()
                try:
                    await page.wait_for_function(
                        """() => {
                            const token = localStorage.getItem('secondclass.tokenv3') || '';
                            return token.split('.').length === 3;
                        }""",
                        timeout=30_000,
                    )
                except PlaywrightTimeoutError as exc:
                    raise RuntimeError(
                        "第二课堂浏览器登录未完成，可能需要人工完成验证码或检查账号密码"
                    ) from exc
                token = await page.evaluate("() => localStorage.getItem('secondclass.tokenv3') || ''")
                return str(token)
            finally:
                await browser.close()

    def _load_credentials(self) -> tuple[str, str]:
        if not self.password_file.is_file():
            raise RuntimeError(f"自动登录凭据文件不存在：{self.password_file}")
        lines = self.password_file.read_text(encoding="utf-8-sig").splitlines()
        if len(lines) < 2 or not lines[0].strip() or not lines[1].strip():
            raise RuntimeError("校园自动登录凭据必须第一行为账号、第二行为密码")
        return lines[0].strip(), lines[1].strip()

    @staticmethod
    def _headless() -> bool:
        return os.getenv("AMADEUS_CAMPUS_BROWSER_HEADLESS", "true").strip().lower() not in {
            "0",
            "false",
            "no",
        }

    @staticmethod
    def _portal_headless() -> bool:
        # BUPT CAS currently returns HTTP 400 for its login iframe in headless
        # Chromium. The window only appears when the portal session has expired.
        return os.getenv("AMADEUS_PORTAL_BROWSER_HEADLESS", "false").strip().lower() not in {
            "0",
            "false",
            "no",
        }

    @staticmethod
    def _activity_headless() -> bool:
        # The site's verification widget may reject headless login. The window
        # appears only while an expired token is being renewed.
        return os.getenv("AMADEUS_ACTIVITY_BROWSER_HEADLESS", "false").strip().lower() not in {
            "0",
            "false",
            "no",
        }

    async def _save_cookie_header(
        self,
        context: BrowserContext,
        target_url: str,
        source: str,
    ) -> None:
        cookies = await context.cookies([target_url])
        if not cookies:
            raise RuntimeError(f"{source} 自动登录成功但没有获得会话 Cookie")
        # RFC 6265 requires longer (more specific) paths first when names repeat.
        cookies.sort(key=lambda item: -len(str(item.get("path") or "/")))
        header = "; ".join(f"{item['name']}={item['value']}" for item in cookies)
        variable = "AMADEUS_PORTAL_COOKIE_FILE" if source == "portal" else "AMADEUS_JWGL_COOKIE_FILE"
        default = "secrets/portal-cookie.txt" if source == "portal" else "secrets/jwgl-cookie.txt"
        path = _resolve_project_path(os.getenv(variable, default))
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(header, encoding="utf-8")
        temporary.replace(path)


def _resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def _real_response_status(response: httpx.Response) -> int:
    value = response.headers.get("x-real-status", "").strip()
    try:
        return int(value) if value else response.status_code
    except ValueError:
        return response.status_code


def _looks_like_jwt(value: object) -> bool:
    return isinstance(value, str) and all(value.split(".")) and len(value.split(".")) == 3


async def _looks_like_jwgl_login(page: Page) -> bool:
    return "/login" in page.url.lower() or await page.locator('input[name="userPassword"]').count() > 0
