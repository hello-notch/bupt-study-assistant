import os
from pathlib import Path

from amadeus_bot.paths import AppPaths
from amadeus_bot.settings import load_project_env


def test_load_project_env_populates_process_environment(tmp_path: Path, monkeypatch) -> None:
    variable = "AMADEUS_TEST_ENV_LOADING"
    monkeypatch.delenv(variable, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(f"{variable}=loaded\n", encoding="utf-8")

    assert load_project_env(env_file) == env_file.resolve()
    assert os.environ[variable] == "loaded"


def test_app_paths_exposes_project_backup_directory(tmp_path: Path) -> None:
    paths = AppPaths(
        project_root=tmp_path,
        data=tmp_path / "data",
        logs=tmp_path / "logs",
        config=tmp_path / "config",
        api_key_file=tmp_path / "apikey.txt",
        ai_routes_file=tmp_path / "routes.toml",
    )

    assert paths.backups == tmp_path / "backups"
