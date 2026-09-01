"""Save campus Cookie headers through a small local, masked GUI.

The values are never printed or passed as command-line arguments.
"""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox

from configure_campus_secrets import (
    SECRETS_DIR,
    normalize_cookie_header,
    protect_secrets_directory,
)


class CookieConfigurator:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("邮学伴校园 Cookie 配置")
        self.root.resizable(False, False)
        self.portal = tk.StringVar()
        self.jwgl = tk.StringVar()
        self.electricity = tk.StringVar()

        frame = tk.Frame(root, padx=18, pady=16)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text="从开发者工具复制完整 Cookie 请求头，然后粘贴到对应框中。\n"
            "内容会被遮蔽，且不会输出到终端或日志。",
            justify="left",
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        self._add_secret_row(frame, 1, "信息门户 Cookie", self.portal)
        self._add_secret_row(frame, 2, "教务系统 Cookie", self.jwgl)
        self._add_secret_row(frame, 3, "电费系统 Cookie", self.electricity)

        tk.Button(frame, text="保存已填写的 Cookie", command=self.save, width=20).grid(
            row=4, column=0, columnspan=3, pady=(16, 0)
        )

    def _add_secret_row(self, frame: tk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        tk.Label(frame, text=label).grid(row=row, column=0, sticky="e", pady=6)
        entry = tk.Entry(frame, textvariable=variable, show="●", width=58)
        entry.grid(row=row, column=1, padx=8, pady=6)
        tk.Button(
            frame,
            text="从剪贴板粘贴",
            command=lambda: self.paste(variable),
        ).grid(row=row, column=2, pady=6)

    def paste(self, variable: tk.StringVar) -> None:
        try:
            value = self.root.clipboard_get().strip()
        except tk.TclError:
            messagebox.showerror("无法粘贴", "剪贴板中没有文本。")
            return
        variable.set(value)

    def save(self) -> None:
        portal_raw = self.portal.get().strip()
        jwgl_raw = self.jwgl.get().strip()
        electricity_raw = self.electricity.get().strip()
        if not portal_raw and not jwgl_raw and not electricity_raw:
            messagebox.showerror("无法保存", "请至少填写一项完整的 Cookie 请求头。")
            return

        try:
            portal_cookie = normalize_cookie_header(portal_raw) if portal_raw else ""
            jwgl_cookie = normalize_cookie_header(jwgl_raw) if jwgl_raw else ""
            electricity_cookie = normalize_cookie_header(electricity_raw) if electricity_raw else ""
        except SystemExit as exc:
            messagebox.showerror("无法保存", str(exc))
            return

        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        saved = []
        if portal_cookie:
            (SECRETS_DIR / "portal-cookie.txt").write_text(portal_cookie, encoding="utf-8")
            saved.append("信息门户")
        if jwgl_cookie:
            (SECRETS_DIR / "jwgl-cookie.txt").write_text(jwgl_cookie, encoding="utf-8")
            saved.append("教务系统")
        if electricity_cookie:
            (SECRETS_DIR / "electricity-cookie.txt").write_text(electricity_cookie, encoding="utf-8")
            saved.append("电费系统")
        protected = protect_secrets_directory()
        self.portal.set("")
        self.jwgl.set("")
        self.electricity.set("")
        messagebox.showinfo(
            "保存成功",
            "、".join(saved) + " Cookie 已保存。\n目录 ACL：" + ("已限制" if protected else "未自动修改"),
        )
        self.root.destroy()


def main() -> None:
    migrate_legacy_portal_cookie()
    root = tk.Tk()
    CookieConfigurator(root)
    root.mainloop()


def migrate_legacy_portal_cookie() -> None:
    """Migrate the portal's old mapping format; JWGL must be recopied due duplicates."""
    target = SECRETS_DIR / "portal-cookie.txt"
    legacy = SECRETS_DIR / "portal-cookies.json"
    if target.exists() or not legacy.is_file():
        return
    payload = json.loads(legacy.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        return
    target.write_text(
        "; ".join(f"{key}={value}" for key, value in payload.items()),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
