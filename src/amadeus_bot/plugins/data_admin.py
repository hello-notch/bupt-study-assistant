from __future__ import annotations

import json
import secrets
import shutil
import sqlite3
import time
import zipfile
from datetime import datetime
from pathlib import Path

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from amadeus_bot.bootstrap import get_container
from amadeus_bot.domain.commands import CommandSpec, command_registry
from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.plugins.common import finish_text_or_image

command_registry.register(
    CommandSpec(
        name="data",
        description="创建数据备份并管理数据保留策略",
        usage="/data backup | backups | restore <archive> [token] | migrate | retention [days]",
        permission=PermissionLevel.SUPERUSER,
        ai_callable=False,
    )
)

data_command = on_command("data", permission=SUPERUSER, priority=5, block=True)
_restore_tokens: dict[str, tuple[str, str, float]] = {}


@data_command.handle()
async def handle_data(event, arguments: Message = CommandArg()) -> None:
    tokens = arguments.extract_plain_text().split()
    action = tokens[0] if tokens else "backups"
    paths = get_container().paths
    backup_root = paths.backups
    backup_root.mkdir(parents=True, exist_ok=True)
    if action == "backup":
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive = await __import__("asyncio").to_thread(
            shutil.make_archive, str(backup_root / f"amadeus-{stamp}"), "zip", paths.data
        )
        await data_command.finish(
            f"备份完成：{Path(archive).name}\n仅包含 data，不包含 .env、API key 或日志。"
        )
    if action == "backups":
        rows = sorted(backup_root.glob("amadeus-*.zip"), reverse=True)
        text = "\n".join(f"{path.name} · {path.stat().st_size / 1024 / 1024:.2f} MiB" for path in rows[:50])
        await finish_text_or_image(data_command, text or "没有备份。", title="数据备份")
    if action == "restore":
        if len(tokens) not in {2, 3}:
            await data_command.finish("用法：/data restore <备份文件名> [confirm_token]")
        archive = (backup_root / Path(tokens[1]).name).resolve()
        if archive.parent != backup_root.resolve() or not archive.is_file() or archive.suffix != ".zip":
            await data_command.finish("备份文件不存在或文件名不合法。")
        if len(tokens) == 2:
            try:
                summary = _inspect_backup(archive, backup_root)
            except (ValueError, zipfile.BadZipFile) as exc:
                await data_command.finish(f"备份校验失败：{exc}")
            token = secrets.token_urlsafe(8)
            _restore_tokens[token] = (
                str(archive),
                event.get_user_id(),
                time.monotonic() + 300,
            )
            await data_command.finish(
                f"恢复预检通过：{summary}\n该操作会先备份当前 data，并保留旧目录。"
                f"请在 5 分钟内确认：/data restore {archive.name} {token}"
            )
        expected = _restore_tokens.pop(tokens[2], None)
        if (
            not expected
            or expected[0] != str(archive)
            or expected[1] != event.get_user_id()
            or expected[2] < time.monotonic()
        ):
            await data_command.finish("确认 token 无效或已过期。")
        try:
            _inspect_backup(archive, backup_root)
        except (ValueError, zipfile.BadZipFile) as exc:
            await data_command.finish(f"备份在确认前发生变化或已损坏：{exc}")
        old_directory, snapshot = _restore_backup(paths.data, archive, backup_root)
        await data_command.finish(
            f"恢复完成。恢复前快照：{snapshot.name}\n"
            f"被替换目录：{old_directory.name}\n建议立即重启 Bot 并执行 /data migrate。"
        )
    if action == "migrate":
        counts = _migrate_all()
        await data_command.finish(
            f"迁移完成：core=1，用户库={counts[0]}，群库={counts[1]}。该操作可重复执行。"
        )
    if action == "retention":
        config_path = paths.data / "shared" / "retention.json"
        if len(tokens) == 1:
            current = (
                json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {"days": 90}
            )
            await data_command.finish(f"当前消息/媒体保留策略：{current['days']} 天。")
        if len(tokens) != 2 or not tokens[1].isdigit() or not 7 <= int(tokens[1]) <= 3650:
            await data_command.finish("用法：/data retention <7-3650 天>")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"days": int(tokens[1]), "updated_by": event.get_user_id()}),
            encoding="utf-8",
        )
        await data_command.finish(f"已将保留策略设为 {tokens[1]} 天；清理任务只处理超过期限的日志和缓存。")
    await data_command.finish(
        "/data backup | backups | restore <archive> [token] | migrate | retention [days]"
    )


def _inspect_backup(archive: Path, backup_root: Path) -> str:
    staging = backup_root / f"restore-check-{secrets.token_hex(6)}"
    staging.mkdir(parents=True)
    try:
        count = _safe_extract(archive, staging)
        core = staging / "core.sqlite3"
        if not core.is_file():
            raise ValueError("备份中缺少 core.sqlite3")
        with sqlite3.connect(core) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("core.sqlite3 完整性校验失败")
        return f"{count} 个文件，core.sqlite3 完整"
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _restore_backup(data_root: Path, archive: Path, backup_root: Path) -> tuple[Path, Path]:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot = Path(shutil.make_archive(str(backup_root / f"pre-restore-{stamp}"), "zip", data_root))
    staging = backup_root / f"restore-stage-{secrets.token_hex(6)}"
    staging.mkdir(parents=True)
    _safe_extract(archive, staging)
    old_directory = backup_root / f"replaced-data-{stamp}"
    if old_directory.exists():
        old_directory = backup_root / f"replaced-data-{stamp}-{secrets.token_hex(3)}"
    shutil.move(str(data_root), str(old_directory))
    try:
        shutil.move(str(staging), str(data_root))
    except Exception:
        shutil.move(str(old_directory), str(data_root))
        raise
    return old_directory, snapshot


def _safe_extract(archive: Path, destination: Path) -> int:
    destination_resolved = destination.resolve()
    count = 0
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if destination_resolved not in target.parents and target != destination_resolved:
                raise ValueError("ZIP 含有越界路径")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            count += 1
    return count


def _migrate_all() -> tuple[int, int]:
    container = get_container()
    container.database.initialize()
    users = 0
    if container.user_repository.users_root.exists():
        for directory in container.user_repository.users_root.iterdir():
            if directory.is_dir() and directory.name.isdigit():
                with container.user_repository.connection(directory.name):
                    users += 1
    groups = 0
    groups_root = container.group_repository.groups_root
    if groups_root.exists():
        for directory in groups_root.iterdir():
            if directory.is_dir() and directory.name.isdigit():
                with container.group_repository.connection(directory.name):
                    groups += 1
    return users, groups
