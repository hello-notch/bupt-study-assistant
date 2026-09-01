"""Renew one web campus session without exposing credentials to Node or logs."""

from __future__ import annotations

import asyncio
import json
import sys

from amadeus_bot.services.campus_auth import CampusAuthenticator


async def renew(source: str) -> None:
    authenticator = CampusAuthenticator()
    if not authenticator.available:
        raise RuntimeError("未配置校园自动登录凭据")
    if source == "portal":
        await authenticator.login_portal()
    elif source == "jwgl":
        await authenticator.login_jwgl()
    elif source == "activity":
        await authenticator.login_activity()
    else:
        raise RuntimeError("不支持的校园数据源")


def main() -> None:
    source = sys.argv[1] if len(sys.argv) == 2 else ""
    try:
        asyncio.run(renew(source))
    except Exception as exc:  # The caller needs a safe, user-facing reason.
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return
    print(json.dumps({"ok": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
