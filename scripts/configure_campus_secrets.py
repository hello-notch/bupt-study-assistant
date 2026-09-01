"""Interactively save campus cookies/tokens without echoing them to the terminal.

Never pass secrets as command-line arguments. Run this script, choose a source,
then paste the value only at the hidden prompt.
"""

from __future__ import annotations

import csv
import getpass
import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS_DIR = PROJECT_ROOT / "secrets"


def main() -> None:
    print("选择要配置的凭据：")
    print("  1. 信息门户 Cookie 请求头")
    print("  2. 教务系统 Cookie 请求头")
    print("  3. 第二课堂 Authorization Bearer token")
    print("  4. 电费系统 Cookie 请求头")
    print("  5. 依次配置以上四项")
    print("  6. 校园自动登录账号和密码（推荐，可自动续期前三项）")
    choice = input("请输入 1/2/3/4/5/6：").strip()
    if choice not in {"1", "2", "3", "4", "5", "6"}:
        raise SystemExit("无效选择")

    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    acl_protected = protect_secrets_directory()
    choices = ("1", "2", "3", "4") if choice == "5" else (choice,)
    for current_choice in choices:
        configure_one(current_choice, acl_protected)


def configure_one(choice: str, acl_protected: bool) -> None:
    if choice == "6":
        account = getpass.getpass("输入统一身份认证账号（输入不会显示）：").strip()
        password = getpass.getpass("输入统一身份认证密码（输入不会显示）：").strip()
        if not account or not password or "\n" in account or "\n" in password:
            raise SystemExit("账号和密码必须是非空单行文本")
        path = SECRETS_DIR / "campus-password.txt"
        path.write_text(f"{account}\n{password}\n", encoding="utf-8")
        variable = "YOUXUEBAN_CAMPUS_PASSWORD_FILE"
    elif choice in {"1", "2", "4"}:
        source = {"1": "信息门户", "2": "教务系统", "4": "电费系统"}[choice]
        raw = getpass.getpass(f"粘贴{source}的完整 Cookie 请求头（输入不会显示）：").strip()
        cookie_header = normalize_cookie_header(raw)
        filename = {"1": "portal-cookie.txt", "2": "jwgl-cookie.txt", "4": "electricity-cookie.txt"}[choice]
        path = SECRETS_DIR / filename
        path.write_text(cookie_header, encoding="utf-8")
        variable = {
            "1": "YOUXUEBAN_PORTAL_COOKIE_FILE",
            "2": "YOUXUEBAN_JWGL_COOKIE_FILE",
            "4": "YOUXUEBAN_ELECTRICITY_COOKIE_FILE",
        }[choice]
    else:
        token = getpass.getpass("粘贴 Authorization 值或 Bearer 后的 token（输入不会显示）：").strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token:
            raise SystemExit("token 不能为空")
        path = SECRETS_DIR / "activity-token.txt"
        path.write_text(token, encoding="utf-8")
        variable = "YOUXUEBAN_ACTIVITY_TOKEN_FILE"

    print(f"已保存到：{path}")
    print("目录 ACL：" + ("已限制为当前 Windows 用户和 SYSTEM" if acl_protected else "未自动修改"))
    print("请把下面一行加入 .env（只包含文件路径，不包含凭据）：")
    print(f"{variable}=secrets/{path.name}")


def normalize_cookie_header(raw: str) -> str:
    raw = raw.strip()
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].lstrip()
    if not raw or "\r" in raw or "\n" in raw:
        raise SystemExit("Cookie 必须是单行请求头")
    parts = [part.strip() for part in raw.split(";") if part.strip()]
    if not parts or any("=" not in part or not part.partition("=")[0] for part in parts):
        raise SystemExit("没有解析到有效 Cookie")
    return "; ".join(parts)


def protect_secrets_directory() -> bool:
    if os.name != "nt":
        return False
    try:
        whoami = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
        _identity, sid = next(csv.reader([whoami]))
        subprocess.run(
            [
                "icacls",
                str(SECRETS_DIR),
                "/inheritance:r",
                "/grant:r",
                f"*{sid}:(OI)(CI)F",
                "*S-1-5-18:(OI)(CI)F",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError, StopIteration, ValueError):
        return False
    return True


if __name__ == "__main__":
    main()
