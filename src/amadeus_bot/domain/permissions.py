from __future__ import annotations

from enum import StrEnum


class PermissionLevel(StrEnum):
    EVERYONE = "EVERYONE"
    MEMBER = "MEMBER"
    SUPERUSER = "SUPERUSER"
    OWNER_OR_MEMBER = "OWNER_OR_MEMBER"
    SELF_OR_SUPERUSER = "SELF_OR_SUPERUSER"


class Capability(StrEnum):
    AI_MEMBER_DELEGATE = "AI_MEMBER_DELEGATE"


def can_use_role(actual: PermissionLevel, required: PermissionLevel) -> bool:
    role_rank = {
        PermissionLevel.EVERYONE: 0,
        PermissionLevel.MEMBER: 1,
        PermissionLevel.SUPERUSER: 2,
    }
    if actual not in role_rank or required not in role_rank:
        return False
    return role_rank[actual] >= role_rank[required]
