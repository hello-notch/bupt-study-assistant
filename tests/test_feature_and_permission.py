from pathlib import Path

from amadeus_bot.domain.permissions import PermissionLevel
from amadeus_bot.repositories.core import CoreRepository
from amadeus_bot.repositories.database import CoreDatabase
from amadeus_bot.services.feature_flags import FeatureFlagService
from amadeus_bot.services.permission import PermissionService


def make_services(path: Path):
    database = CoreDatabase(path / "core.sqlite3")
    database.initialize()
    repository = CoreRepository(database)
    return repository, FeatureFlagService(repository), PermissionService(repository, {"999"})


def test_feature_precedence_and_reset(tmp_path: Path) -> None:
    _, features, _ = make_services(tmp_path)
    assert features.status("chat", "100").enabled is True

    features.set("chat", "global", False, "999")
    assert features.status("chat", "100").enabled is False
    assert features.status("chat", "100").source == "global"

    features.set("chat", "100", True, "999")
    assert features.status("chat", "100").enabled is True
    assert features.status("chat", "100").source == "group"

    features.reset("chat", "100")
    assert features.status("chat", "100").enabled is False
    assert features.status("chat", "100").source == "global"


def test_superuser_can_manage_self_scoped_resources(tmp_path: Path) -> None:
    repository, _, permissions = make_services(tmp_path)
    repository.add_member("200", "999")

    assert permissions.role_for("100") == PermissionLevel.EVERYONE
    assert permissions.role_for("200") == PermissionLevel.MEMBER
    assert permissions.role_for("999") == PermissionLevel.SUPERUSER
    assert permissions.can_access_self_resource("100", "100")
    assert permissions.can_access_self_resource("999", "100")
    assert not permissions.can_access_self_resource("200", "100")


def test_ignore_rules_respect_scope(tmp_path: Path) -> None:
    repository, features, _ = make_services(tmp_path)
    repository.add_ignore_rule("100", "group", "1", "999")
    assert features.is_ignored("100", "1", "ai")
    assert not features.is_ignored("100", "2", "ai")
