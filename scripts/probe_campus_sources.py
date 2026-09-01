"""Probe configured campus sources without printing credentials or response bodies."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from amadeus_bot.repositories.core import CoreRepository
from amadeus_bot.repositories.database import CoreDatabase
from amadeus_bot.services.campus import (
    ActivitySource,
    PortalSource,
    decode_portal_html,
    load_cookie_header_file,
    parse_portal_list,
)

ROOT = Path(__file__).resolve().parents[1]
SECRETS = ROOT / "secrets"


def cookie_headers(name: str) -> dict[str, str]:
    value = load_cookie_header_file(str(SECRETS / name))
    return {"Cookie": value} if value else {}


def safe_url(value: str) -> str:
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def page_title(text: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", text, re.I | re.S)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


async def probe_portal() -> dict:
    url = "http://my.bupt.edu.cn/list.jsp?urltype=tree.TreeTempUrl&wbtreeid=1154"
    async with httpx.AsyncClient(
        headers=cookie_headers("portal-cookie.txt"),
        follow_redirects=True,
        timeout=20.0,
    ) as client:
        response = await client.get(url)
    login_redirect = "authserver/login" in str(response.url).lower()
    decoded_text = decode_portal_html(response.content)
    charset_match = re.search(rb"charset\s*=\s*['\"]?([A-Za-z0-9_-]+)", response.content[:4096], re.I)
    gb18030_text = response.content.decode("gb18030", errors="replace")
    return {
        "status": response.status_code,
        "final_url": safe_url(str(response.url)),
        "login_redirect": login_redirect,
        "title": page_title(decoded_text),
        "declared_charset": charset_match.group(1).decode("ascii") if charset_match else None,
        "gb18030_title": page_title(gb18030_text),
        "parsed_items": 0 if login_redirect else len(parse_portal_list(decoded_text, str(response.url))),
    }


async def probe_jwgl() -> dict:
    url = "https://jwgl.bupt.edu.cn/jsxsd/framework/xsMain_bjyddx.jsp"
    async with httpx.AsyncClient(
        headers=cookie_headers("jwgl-cookie.txt"),
        follow_redirects=True,
        timeout=20.0,
    ) as client:
        response = await client.get(url)
    title = page_title(response.text)
    login_redirect = "login" in str(response.url).lower() or "用户登录" in response.text
    return {
        "status": response.status_code,
        "final_url": safe_url(str(response.url)),
        "login_redirect": login_redirect,
        "title": title,
        "has_class_query_form": "querySkbj" in response.text or "班级" in response.text,
    }


async def probe_activity() -> dict:
    token = (SECRETS / "activity-token.txt").read_text(encoding="utf-8").strip()
    url = "https://dekt.bupt.edu.cn/api/v1/participation/admin/act"
    params = {
        "act_state": 0,
        "page": 1,
        "page_size": 50,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            url,
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    result = {
        "status": response.status_code,
        "final_url": safe_url(str(response.url)),
        "content_type": response.headers.get("content-type", "").split(";", 1)[0],
    }
    if response.headers.get("content-type", "").startswith("application/json"):
        payload = response.json()
        result["top_level_keys"] = list(payload) if isinstance(payload, dict) else []
        data = payload.get("data") if isinstance(payload, dict) else payload
        result["items"] = len(data) if isinstance(data, list) else None
    elif response.status_code >= 400:
        result["error_preview"] = response.text[:300]
    return result


async def probe_service_layer() -> dict:
    os.environ["AMADEUS_PORTAL_COOKIE_FILE"] = str(SECRETS / "portal-cookie.txt")
    os.environ["AMADEUS_ACTIVITY_TOKEN_FILE"] = str(SECRETS / "activity-token.txt")
    os.environ["AMADEUS_ACTIVITY_LIST_ENDPOINT"] = "/api/v1/participation/admin/act"
    with tempfile.TemporaryDirectory(prefix="amadeus-campus-probe-") as directory:
        database = CoreDatabase(Path(directory) / "core.sqlite3")
        database.initialize()
        repository = CoreRepository(database)
        portal_result = await PortalSource(repository).refresh()
        activity_result = await ActivitySource(repository).refresh()
        return {
            "portal_refresh": portal_result,
            "portal_health": repository.get_source_health("portal"),
            "activity_refresh": activity_result,
            "activity_health": repository.get_source_health("activity"),
        }


async def probe_activity_service() -> dict:
    os.environ["AMADEUS_ACTIVITY_TOKEN_FILE"] = str(SECRETS / "activity-token.txt")
    os.environ["AMADEUS_ACTIVITY_LIST_ENDPOINT"] = "/api/v1/participation/admin/act"
    with tempfile.TemporaryDirectory(prefix="amadeus-activity-probe-") as directory:
        database = CoreDatabase(Path(directory) / "core.sqlite3")
        database.initialize()
        repository = CoreRepository(database)
        refresh = await ActivitySource(repository).refresh()
        return {
            "activity_refresh": refresh,
            "activity_health": repository.get_source_health("activity"),
        }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--activity-only", action="store_true")
    options = parser.parse_args()
    if options.activity_only:
        try:
            result = await probe_activity_service()
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps({"activity_service": result}, ensure_ascii=False, indent=2))
        return

    results = {}
    for name, probe in (
        ("portal", probe_portal),
        ("jwgl", probe_jwgl),
        ("activity", probe_activity),
        ("service_layer", probe_service_layer),
    ):
        try:
            results[name] = await probe()
        except Exception as exc:  # Probe must report all three sources.
            results[name] = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
