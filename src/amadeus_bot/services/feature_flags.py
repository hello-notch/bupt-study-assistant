from __future__ import annotations

from dataclasses import dataclass

from amadeus_bot.repositories.core import CoreRepository

DEFAULT_FEATURES: dict[str, bool] = {
    "chat": True,
    "proactive_chat": False,
    "wife": True,
    "recommendation": True,
    "stick": True,
    "poke": True,
    "portal": True,
    "activity": True,
    "stats": True,
    "summary": True,
    "quotes": True,
    "course": True,
    "ddl": True,
    "render": True,
    "memory": True,
    "logs": True,
}


@dataclass(frozen=True, slots=True)
class FeatureStatus:
    feature: str
    enabled: bool
    source: str


class FeatureFlagService:
    def __init__(self, repository: CoreRepository) -> None:
        self.repository = repository

    def registered_features(self) -> tuple[str, ...]:
        return tuple(sorted(DEFAULT_FEATURES))

    def status(self, feature: str, group_id: str | None = None) -> FeatureStatus:
        self._validate_feature(feature)
        rows = self.repository.get_feature_rows(feature)
        global_row = next((row for row in rows if row["scope_type"] == "global"), None)
        group_row = next(
            (
                row
                for row in rows
                if group_id is not None
                and row["scope_type"] == "group"
                and str(row["scope_id"]) == str(group_id)
            ),
            None,
        )
        if group_row is not None:
            return FeatureStatus(feature, bool(group_row["enabled"]), "group")
        if global_row is not None:
            return FeatureStatus(feature, bool(global_row["enabled"]), "global")
        return FeatureStatus(feature, DEFAULT_FEATURES[feature], "default")

    def set(self, feature: str, scope: str, enabled: bool, actor: str) -> FeatureStatus:
        self._validate_feature(feature)
        if scope == "global":
            scope_type, scope_id = "global", ""
            group_id = None
        else:
            if not scope.isdigit():
                raise ValueError("群号必须是数字，或使用 global")
            scope_type, scope_id = "group", scope
            group_id = scope
        self.repository.set_feature(feature, scope_type, scope_id, enabled, str(actor))
        return self.status(feature, group_id)

    def reset(self, feature: str, group_id: str) -> FeatureStatus:
        self._validate_feature(feature)
        if not str(group_id).isdigit():
            raise ValueError("群号必须是数字")
        self.repository.reset_group_feature(feature, str(group_id))
        return self.status(feature, str(group_id))

    def is_ignored(self, user_id: str, group_id: str | None, kind: str) -> bool:
        if kind not in {"ai", "stats"}:
            raise ValueError("忽略类型只能是 ai 或 stats")
        return self.repository.is_ignored(str(user_id), group_id, kind)

    @staticmethod
    def _validate_feature(feature: str) -> None:
        if feature not in DEFAULT_FEATURES:
            names = "、".join(sorted(DEFAULT_FEATURES))
            raise ValueError(f"未知功能 {feature!r}，可用功能：{names}")
