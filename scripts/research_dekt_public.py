"""Read-only inspection of public Second Classroom frontend bundles.

This intentionally never reads browser storage, cookies, or credentials.
"""

from __future__ import annotations

import re

import httpx

BASE = "https://dekt.bupt.edu.cn"
LANDING_CHUNKS = ("2471", "9700", "2898", "5661", "2215", "6798", "4768", "741", "8100", "8654")
ACTIVITY_ENDPOINT = "/api/v1/participation/admin/act"
AUTH_ENDPOINTS = (
    "/api/v1/auth/bupt/sessions",
    "/api/v1/auth/sessions",
)
MODULE_MARKERS = ("14645:function", "54210:function")


def print_endpoint_context(chunk_id: str, url: str, source: str, endpoint: str) -> None:
    position = source.find(endpoint)
    if position < 0:
        return
    start = max(0, position - 1200)
    end = min(len(source), position + 1800)
    print("ENDPOINT_CHUNK", chunk_id, endpoint, url)
    print(source[start:end])


def main() -> None:
    with httpx.Client(timeout=20) as client:
        page = client.get(BASE).text
        script_urls = re.findall(r'<script[^>]+src=["\']([^"\']+)', page)
        script_sources: list[tuple[str, str]] = []
        for script_url in script_urls:
            script_url = script_url if script_url.startswith("http") else f"{BASE}{script_url}"
            script_sources.append((script_url, client.get(script_url).text))
        index_url, index = next((url, source) for url, source in script_sources if "/static/js/index." in url)
        print("INDEX", index_url)
        for url, source in script_sources:
            for marker in MODULE_MARKERS:
                print_endpoint_context("base", url, source, marker)
        hash_block = index[index.find("l.u=function") : index.find("l.miniCssF=function")]
        hashes = dict(re.findall(r'(\d+):"([a-f0-9]{8})"', hash_block))
        for chunk_id in LANDING_CHUNKS:
            digest = hashes.get(chunk_id)
            if not digest:
                continue
            url = f"{BASE}/static/js/async/{chunk_id}.{digest}.js"
            response = client.get(url)
            endpoints = sorted(set(re.findall(r"/api/v1/[A-Za-z0-9_?=&{}:./-]+", response.text)))
            print(chunk_id, response.status_code, len(response.text), url)
            for endpoint in endpoints:
                print("  ", endpoint)

        for chunk_id, digest in hashes.items():
            url = f"{BASE}/static/js/async/{chunk_id}.{digest}.js"
            response = client.get(url)
            for endpoint in (ACTIVITY_ENDPOINT, *AUTH_ENDPOINTS):
                print_endpoint_context(chunk_id, url, response.text, endpoint)


if __name__ == "__main__":
    main()
