from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from amadeus_bot.domain.permissions import PermissionLevel


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    description: str
    usage: str
    permission: PermissionLevel = PermissionLevel.EVERYONE
    aliases: tuple[str, ...] = ()
    feature: str | None = None
    ai_callable: bool = False
    ai_delegate_member: bool = False
    examples: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(slots=True)
class CommandRegistry:
    _commands: dict[str, CommandSpec] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def register(self, spec: CommandSpec) -> CommandSpec:
        with self._lock:
            if spec.name in self._commands and self._commands[spec.name] != spec:
                raise ValueError(f"命令 {spec.name!r} 已注册")
            self._commands[spec.name] = spec
        return spec

    def get(self, name_or_alias: str) -> CommandSpec | None:
        target = name_or_alias.strip().lstrip("/")
        with self._lock:
            direct = self._commands.get(target)
            if direct:
                return direct
            return next((item for item in self._commands.values() if target in item.aliases), None)

    def all(self) -> list[CommandSpec]:
        with self._lock:
            return sorted(self._commands.values(), key=lambda item: item.name)


command_registry = CommandRegistry()
