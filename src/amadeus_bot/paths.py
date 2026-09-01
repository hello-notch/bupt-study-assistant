from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from amadeus_bot.settings import load_project_env


@dataclass(frozen=True, slots=True)
class AppPaths:
    project_root: Path
    data: Path
    logs: Path
    config: Path
    api_key_file: Path
    ai_routes_file: Path

    @classmethod
    def discover(cls) -> AppPaths:
        load_project_env()
        project_root = Path(__file__).resolve().parents[2]
        data = _resolve_from_root(project_root, os.getenv("AMADEUS_DATA_DIR", "data"))
        logs = _resolve_from_root(project_root, os.getenv("AMADEUS_LOG_DIR", "logs"))
        key_file = _resolve_from_root(project_root, os.getenv("AMADEUS_API_KEY_FILE", "secrets/apikey.txt"))
        route_file = _resolve_from_root(
            project_root, os.getenv("AMADEUS_AI_ROUTES_FILE", "config/ai_routes.toml")
        )
        return cls(
            project_root=project_root,
            data=data,
            logs=logs,
            config=project_root / "config",
            api_key_file=key_file,
            ai_routes_file=route_file,
        )

    @property
    def backups(self) -> Path:
        return self.project_root / "backups"

    def ensure_runtime_directories(self) -> None:
        for path in (
            self.data,
            self.logs,
            self.data / "users",
            self.data / "groups",
            self.data / "shared",
            self.data / "cache" / "render",
            self.logs / "runtime",
            self.logs / "audit",
        ):
            path.mkdir(parents=True, exist_ok=True)


def _resolve_from_root(project_root: Path, value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.resolve()
