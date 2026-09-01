import json
from pathlib import Path

from amadeus_bot.repositories.core import CoreRepository
from amadeus_bot.repositories.database import CoreDatabase
from amadeus_bot.repositories.user_data import UserDataRepository
from amadeus_bot.services.ddl import DDLService
from amadeus_bot.services.feature_flags import FeatureFlagService
from amadeus_bot.services.tools import AIToolService, ToolExecutionContext


def make_tools(path: Path) -> AIToolService:
    database = CoreDatabase(path / "core.sqlite3")
    database.initialize()
    core = CoreRepository(database)
    return AIToolService(
        DDLService(UserDataRepository(path / "users")),
        core,
        FeatureFlagService(core),
    )


async def test_ai_tool_subject_must_equal_requester(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    result = json.loads(
        await tools.execute(
            "ddl_list",
            {},
            ToolExecutionContext(requested_by="100", subject_user_id="200", group_id=None),
        )
    )
    assert result["success"] is False


async def test_ai_member_delegate_is_limited_to_registered_tool(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    context = ToolExecutionContext.for_requester("100", "1")

    added = json.loads(
        await tools.execute(
            "recommend_add",
            {"pool": "food", "content": "咖喱饭", "weight": 1},
            context,
        )
    )
    assert added["success"] is True
    assert added["delegated_capability"] == "AI_MEMBER_DELEGATE"

    rejected = json.loads(await tools.execute("feature_disable", {"feature": "chat"}, context))
    assert rejected["success"] is False
