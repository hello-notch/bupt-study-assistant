from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_project_env(env_file: Path | None = None, *, override: bool = False) -> Path:
    """Load the project ``.env`` into ``os.environ`` for service code.

    NoneBot parses ``.env`` into its own Config object, but it intentionally
    does not copy custom values back to the process environment. Some service
    modules use ``os.getenv`` at runtime, so load the same file explicitly.
    Existing process variables keep precedence unless ``override`` is true.
    """

    path = (env_file or PROJECT_ROOT / ".env").resolve()
    if path.is_file():
        load_dotenv(path, override=override)
    return path
