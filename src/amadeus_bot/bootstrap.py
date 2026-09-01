from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from amadeus_bot.adapters.ai_provider import CredentialStore
from amadeus_bot.paths import AppPaths
from amadeus_bot.repositories.core import CoreRepository
from amadeus_bot.repositories.database import CoreDatabase
from amadeus_bot.repositories.group_data import GroupDataRepository
from amadeus_bot.repositories.user_data import UserDataRepository
from amadeus_bot.services.activity_log import ActivityLogService
from amadeus_bot.services.ai_router import AIRouteCatalog, AIService
from amadeus_bot.services.courses import CourseService
from amadeus_bot.services.ddl import DDLService
from amadeus_bot.services.feature_flags import FeatureFlagService
from amadeus_bot.services.memory import MemoryService
from amadeus_bot.services.permission import PermissionService
from amadeus_bot.services.renderer import RenderService
from amadeus_bot.services.tools import AIToolService


@dataclass(slots=True)
class ServiceContainer:
    paths: AppPaths
    database: CoreDatabase
    repository: CoreRepository
    user_repository: UserDataRepository
    group_repository: GroupDataRepository
    permissions: PermissionService
    features: FeatureFlagService
    renderer: RenderService
    ai: AIService
    ddl: DDLService
    courses: CourseService
    memory: MemoryService
    ai_tools: AIToolService
    activity_log: ActivityLogService

    async def close(self) -> None:
        await self.ai.close()
        await self.renderer.close()


_container: ServiceContainer | None = None
_container_lock = Lock()


def build_container(superusers: set[str] | None = None, paths: AppPaths | None = None) -> ServiceContainer:
    app_paths = paths or AppPaths.discover()
    app_paths.ensure_runtime_directories()
    database = CoreDatabase(app_paths.data / "core.sqlite3")
    database.initialize()
    repository = CoreRepository(database)
    user_repository = UserDataRepository(app_paths.data / "users")
    group_repository = GroupDataRepository(app_paths.data / "groups")
    ddl = DDLService(user_repository)
    courses = CourseService(user_repository)
    features = FeatureFlagService(repository)
    activity_log = ActivityLogService(app_paths.logs)
    catalog = AIRouteCatalog.load(app_paths.ai_routes_file)
    credentials = CredentialStore.load(app_paths.api_key_file)
    container = ServiceContainer(
        paths=app_paths,
        database=database,
        repository=repository,
        user_repository=user_repository,
        group_repository=group_repository,
        permissions=PermissionService(repository, superusers or set()),
        features=features,
        renderer=RenderService(app_paths.data / "cache" / "render"),
        ai=AIService(catalog, credentials, repository),
        ddl=ddl,
        courses=courses,
        memory=MemoryService(user_repository),
        ai_tools=AIToolService(
            ddl,
            repository,
            features,
            user_repository,
            group_repository,
            courses,
            app_paths.logs,
            activity_log,
        ),
        activity_log=activity_log,
    )
    return container


def get_container() -> ServiceContainer:
    global _container
    if _container is not None:
        return _container
    with _container_lock:
        if _container is None:
            superusers = _nonebot_superusers()
            _container = build_container(superusers=superusers)
    return _container


def _nonebot_superusers() -> set[str]:
    try:
        from nonebot import get_driver

        return {str(item) for item in get_driver().config.superusers}
    except Exception:
        return set()
