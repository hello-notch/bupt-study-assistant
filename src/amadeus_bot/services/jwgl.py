from __future__ import annotations

import json
import os
import re
from html import unescape

import httpx

from amadeus_bot.services.campus import load_cookie_header_file
from amadeus_bot.services.campus_auth import CampusAuthenticator, CampusSessionExpired


class JwglSource:
    BASE = "https://jwgl.bupt.edu.cn/jsxsd"
    HOME_PATH = "/framework/xsMain_bjyddx.jsp"

    async def keepalive(self) -> None:
        try:
            await self._keepalive_once()
        except CampusSessionExpired:
            authenticator = CampusAuthenticator()
            if not authenticator.available:
                raise
            await authenticator.login_jwgl()
            await self._keepalive_once()

    async def _keepalive_once(self) -> None:
        cookie_header = load_cookie_header_file(os.getenv("AMADEUS_JWGL_COOKIE_FILE"))
        if not cookie_header:
            raise RuntimeError("未配置受保护的教务系统会话文件 AMADEUS_JWGL_COOKIE_FILE")
        async with self._client(cookie_header) as client:
            response = await client.get(self.HOME_PATH)
            response.raise_for_status()
        if _is_login_page(response):
            raise CampusSessionExpired("教务系统登录已失效")

    async def query_class(self, class_number: str, term: str = "") -> tuple[str, list[dict]]:
        try:
            return await self._query_class_once(class_number, term)
        except CampusSessionExpired:
            authenticator = CampusAuthenticator()
            if not authenticator.available:
                raise
            await authenticator.login_jwgl()
            return await self._query_class_once(class_number, term)

    async def _query_class_once(self, class_number: str, term: str = "") -> tuple[str, list[dict]]:
        cookie_header = load_cookie_header_file(os.getenv("AMADEUS_JWGL_COOKIE_FILE"))
        if not cookie_header:
            raise RuntimeError("未配置受保护的教务系统会话文件 AMADEUS_JWGL_COOKIE_FILE")
        async with self._client(cookie_header) as client:
            # The current autocomplete endpoint returns an "非法访问" HTML page
            # even when invoked by the site's own JavaScript.  The schedule
            # endpoint can resolve an exact class number without its internal id.
            payload = {"skbj": class_number, "skbjid": ""}
            if term:
                payload["xnxqh"] = term
            result = await client.post("/kbcx/kbxx_xzb_ifr", data=payload)
            result.raise_for_status()
        if _is_login_page(result):
            raise CampusSessionExpired("教务系统登录已失效")
        if "非法访问" in result.text:
            raise RuntimeError("教务系统拒绝了班级课表查询")
        rows = parse_class_schedule(result.text, class_number)
        if not rows:
            raise RuntimeError("没有解析到课程；请检查班级号、学年学期或教务页面结构")
        return class_number, rows

    def _client(self, cookie_header: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.BASE,
            headers={"Cookie": cookie_header},
            timeout=20.0,
            follow_redirects=True,
        )


def parse_class_lookup(text: str, class_number: str) -> tuple[str, str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = []
    if isinstance(payload, dict):
        payload = payload.get("list") or payload.get("data") or payload.get("results") or [payload]
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            display = str(item.get("bj") or item.get("text") or item.get("label") or item.get("skbj") or "")
            value = str(item.get("xx04id") or item.get("id") or item.get("value") or item.get("skbjid") or "")
            if class_number in display and value:
                return value, display
    raise RuntimeError("未找到匹配班级号")


def parse_class_schedule(html_text: str, class_number: str = "") -> list[dict]:
    tr_blocks = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html_text, re.I)
    target = next(
        (
            block
            for block in tr_blocks
            if "kbcontent1" in block and (not class_number or class_number in _strip_html(block))
        ),
        "",
    )
    cells = re.findall(r"<td[^>]*>([\s\S]*?)</td>", target, re.I)
    if len(cells) < 8:
        return []
    schedule_cells = cells[1:]
    section_count = len(schedule_cells) // 7
    if section_count < 1:
        return []

    merged: dict[tuple, dict] = {}
    for index, cell in enumerate(schedule_cells[: section_count * 7]):
        weekday = index // section_count + 1
        section = index % section_count + 1
        blocks = re.findall(
            r'<div[^>]*class=["\'][^"\']*kbcontent1[^"\']*["\'][^>]*>([\s\S]*?)</div>',
            cell,
            re.I,
        )
        for block in blocks:
            lines = _html_lines(block)
            week_index = next(
                (i for i, line in enumerate(lines) if re.fullmatch(r"\(([^)]+)周\)", line)),
                None,
            )
            if week_index is None or week_index < 2 or week_index + 1 >= len(lines):
                continue
            teacher = lines[week_index - 1]
            name_parts = [line for line in lines[: week_index - 1] if line != class_number]
            name = " ".join(name_parts).strip()
            if class_number and name.endswith(class_number):
                name = name[: -len(class_number)].strip()
            weeks = re.fullmatch(r"\(([^)]+)周\)", lines[week_index]).group(1)
            location = lines[week_index + 1]
            if not name:
                continue
            key = (name, teacher, weeks, location, weekday)
            if key not in merged:
                merged[key] = {
                    "name": name,
                    "teacher": teacher,
                    "location": location,
                    "weekday": weekday,
                    "start_section": section,
                    "end_section": section,
                    "weeks": weeks.replace("～", "-").replace("~", "-"),
                    "campus": "",
                }
            else:
                merged[key]["start_section"] = min(merged[key]["start_section"], section)
                merged[key]["end_section"] = max(merged[key]["end_section"], section)
    return list(merged.values())


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", value))).strip()


def _html_lines(value: str) -> list[str]:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", "", text))
    return [line.strip() for line in text.splitlines() if line.strip()]


def _is_login_page(response: httpx.Response) -> bool:
    url = str(response.url).lower()
    text = response.text.lower()
    return (
        "login" in url
        or "用户登录" in response.text
        or "<title>登录</title>" in response.text
        or ("请输入账号" in response.text and "请输入密码" in response.text)
        or ("password" in text and "登 录" in response.text)
    )
