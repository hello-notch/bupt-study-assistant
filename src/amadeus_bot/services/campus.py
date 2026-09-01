from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

import httpx

from amadeus_bot.repositories.core import CoreRepository
from amadeus_bot.services.campus_auth import CampusAuthenticator, CampusSessionExpired


@dataclass(frozen=True, slots=True)
class CampusItem:
    item_id: str
    title: str
    published_at: str | None
    department: str
    summary: str
    url: str
    metadata: dict

    def as_repository_item(self) -> dict:
        payload = {
            "item_id": self.item_id,
            "title": self.title,
            "published_at": self.published_at,
            "department": self.department,
            "summary": self.summary,
            "url": self.url,
            "metadata": self.metadata,
        }
        payload["content_hash"] = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        return payload


class PortalSource:
    LIST_URL = "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154"

    def __init__(self, repository: CoreRepository) -> None:
        self.repository = repository

    async def refresh(self) -> tuple[int, int]:
        try:
            return await self._refresh_once()
        except CampusSessionExpired:
            authenticator = CampusAuthenticator()
            if not authenticator.available:
                raise
            await authenticator.login_portal()
            return await self._refresh_once()

    async def _refresh_once(self) -> tuple[int, int]:
        cookie_header = load_cookie_header_file(os.getenv("AMADEUS_PORTAL_COOKIE_FILE"))
        headers = {"Cookie": cookie_header} if cookie_header else {}
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(self.LIST_URL)
            response.raise_for_status()
        html_text = decode_portal_html(response.content)
        if "authserver/login" in str(response.url) or "CAS Login" in html_text:
            raise CampusSessionExpired("信息门户登录已失效")
        items = parse_portal_list(html_text, str(response.url))
        if not items:
            raise RuntimeError("信息门户列表为空，可能是页面结构变化")
        new_count = sum(
            self.repository.upsert_source_item("portal", item.as_repository_item()) for item in items
        )
        self.repository.set_source_health("portal", success=True, item_count=len(items))
        return len(items), new_count


class ActivitySource:
    BASE_URL = "https://dekt.bupt.edu.cn"

    def __init__(self, repository: CoreRepository) -> None:
        self.repository = repository

    async def refresh(self) -> tuple[int, int]:
        endpoint = os.getenv("AMADEUS_ACTIVITY_LIST_ENDPOINT", "").strip()
        if not endpoint:
            raise RuntimeError(
                "尚未配置只读活动列表接口；当前已确认平台使用 Bearer token，但未确认学生端列表路径"
            )
        if not endpoint.startswith("/api/"):
            raise RuntimeError("活动接口必须是站内 /api/... 路径")

        token_file = os.getenv("AMADEUS_ACTIVITY_TOKEN_FILE", "secrets/activity-token.txt")
        token = _load_secret_file(token_file)
        authenticator = CampusAuthenticator()
        if not token:
            if not authenticator.available:
                raise RuntimeError("第二课堂 token 缺失，且未配置可用于自动续登的密码文件")
            await authenticator.login_activity()
            token = _load_secret_file(token_file)

        try:
            return await self._refresh_once(endpoint, token)
        except CampusSessionExpired:
            if not authenticator.available:
                raise
            await authenticator.login_activity()
            refreshed_token = _load_secret_file(token_file)
            if not refreshed_token or refreshed_token == token:
                raise RuntimeError("第二课堂自动续登后未获得新 token") from None
            return await self._refresh_once(endpoint, refreshed_token)

    async def _refresh_once(self, endpoint: str, token: str) -> tuple[int, int]:
        async with httpx.AsyncClient(base_url=self.BASE_URL, timeout=20.0) as client:
            response = await client.get(
                endpoint,
                params={"act_state": 0, "page": 1, "page_size": 50},
                headers={"Authorization": f"Bearer {token}"},
            )
            if response.status_code in {401, 403}:
                raise CampusSessionExpired("第二课堂登录已失效")
            response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("第二课堂活动接口返回了非 JSON 响应") from exc
        items = normalize_activity_payload(payload)
        return self.import_items(items)

    def import_items(self, items: list[CampusItem]) -> tuple[int, int]:
        new_count = sum(
            self.repository.upsert_source_item("activity", item.as_repository_item()) for item in items
        )
        self.repository.prune_source_items("activity", [item.item_id for item in items])
        self.repository.set_source_health("activity", success=True, item_count=len(items))
        return len(items), new_count

    def import_file(self, content: bytes, filename: str) -> tuple[int, int]:
        if filename.lower().endswith(".json"):
            raw = json.loads(content.decode("utf-8-sig"))
            items = normalize_activity_payload(raw)
        elif filename.lower().endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(content.decode("utf-8-sig"))))
            items = [activity_from_mapping(row) for row in rows]
        else:
            raise ValueError("活动导入仅支持 JSON 或 CSV")
        return self.import_items(items)


def parse_portal_list(html_text: str, base_url: str) -> list[CampusItem]:
    text = re.sub(r"<script[\s\S]*?</script>", "", html_text, flags=re.I)
    pattern = re.compile(
        r'<a[^>]+href=["\'](?P<url>[^"\']*(?:xntz_content\.jsp|wbnewsid=)[^"\']*)["\'][^>]*>'
        r"(?P<title>[\s\S]*?)</a>(?P<tail>[\s\S]{0,300})",
        re.I,
    )
    items: list[CampusItem] = []
    seen: set[str] = set()
    for match in pattern.finditer(text):
        url = urljoin(base_url, unescape(match.group("url")))
        id_match = re.search(r"wbnewsid=(\d+)", url)
        item_id = id_match.group(1) if id_match else hashlib.sha256(url.encode()).hexdigest()[:20]
        if item_id in seen:
            continue
        title = _strip_html(match.group("title"))
        date_match = re.search(r"20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}", match.group("tail"))
        if not title:
            continue
        items.append(
            CampusItem(
                item_id,
                title,
                date_match.group(0).replace("/", "-") if date_match else None,
                "",
                "",
                url,
                {},
            )
        )
        seen.add(item_id)
    return items


def decode_portal_html(content: bytes) -> str:
    """Decode portal HTML without turning valid UTF-8 Chinese into mojibake."""
    # The portal has served both UTF-8 and GB18030 pages.  UTF-8 must be tried
    # first: decoding UTF-8 bytes as GB18030 often succeeds but produces the
    # characteristic ``鍖椾含`` style mojibake instead of raising an error.
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("gb18030", errors="replace")


def normalize_activity_payload(payload) -> list[CampusItem]:
    if isinstance(payload, dict):
        for key in ("data", "items", "list", "records", "activities", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                payload = value
                break
            if isinstance(value, dict):
                nested = normalize_activity_payload(value)
                if nested:
                    return nested
    if not isinstance(payload, list):
        return []
    return [activity_from_mapping(item) for item in payload if isinstance(item, dict)]


def activity_from_mapping(item: dict) -> CampusItem:
    item_id = _first(item, "activity_id", "act_id", "id", "活动ID")
    title = _first(item, "name", "title", "activity_name", "act_name", "活动名称")
    if not item_id or not title:
        raise ValueError("活动数据必须包含活动 ID 和名称")
    published = _first(item, "start_time", "activity_time", "begin_at", "活动时间") or None
    metadata = {
        "category": _first(item, "category", "class_name", "type", "类别"),
        "campus": _first(item, "campus", "校区"),
        "location": _first(item, "location", "address", "地点"),
        "registration_start": _first(item, "registration_start", "signup_start", "报名开始"),
        "registration_end": _first(item, "registration_end", "signup_end", "报名结束"),
        "capacity": _first(item, "capacity", "quota", "名额"),
        "status": _first(item, "status", "state", "状态"),
    }
    return CampusItem(
        str(item_id),
        str(title),
        str(published) if published else None,
        str(_first(item, "organizer", "department", "主办方")),
        str(_first(item, "summary", "description", "简介")),
        str(_first(item, "url", "link", "详情链接")),
        metadata,
    )


def load_cookie_header_file(value: str | None) -> str:
    """Load an exact Cookie request header while accepting legacy JSON files."""
    if not value:
        return ""
    path = Path(value).expanduser()
    if not path.is_file():
        return ""
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return "; ".join(f"{key}={item}" for key, item in payload.items())
    if "\r" in raw or "\n" in raw:
        raise RuntimeError("Cookie 文件必须只包含单行请求头")
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].lstrip()
    if not all("=" in part for part in raw.split(";") if part.strip()):
        raise RuntimeError("Cookie 请求头格式无效")
    return "; ".join(part.strip() for part in raw.split(";") if part.strip())


def _load_secret_file(value: str | None) -> str:
    if not value:
        return ""
    path = Path(value).expanduser()
    return path.read_text(encoding="utf-8").strip() if path.is_file() else ""


def _first(item: dict, *keys: str):
    for key in keys:
        if item.get(key) not in {None, ""}:
            return item[key]
    return ""


def _strip_html(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", value))).strip()
