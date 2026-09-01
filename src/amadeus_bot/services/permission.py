from __future__ import annotations

from amadeus_bot.domain.permissions import PermissionLevel, can_use_role
from amadeus_bot.repositories.core import CoreRepository


class PermissionService:
    def __init__(self, repository: CoreRepository, superusers: set[str]) -> None:
        self.repository = repository
        self.superusers = {str(item) for item in superusers}

    def role_for(self, user_id: str) -> PermissionLevel:
        normalized = str(user_id)
        if normalized in self.superusers:
            return PermissionLevel.SUPERUSER
        if self.repository.is_member(normalized):
            return PermissionLevel.MEMBER
        return PermissionLevel.EVERYONE

    def has_role(self, user_id: str, required: PermissionLevel) -> bool:
        return can_use_role(self.role_for(user_id), required)

    def can_access_self_resource(self, actor_id: str, subject_user_id: str) -> bool:
        return str(actor_id) == str(subject_user_id) or self.role_for(actor_id) == PermissionLevel.SUPERUSER

    def can_manage_recommendation(self, actor_id: str, creator_id: str) -> bool:
        return str(actor_id) == str(creator_id) or self.has_role(actor_id, PermissionLevel.MEMBER)
