from pathlib import Path

from amadeus_bot.repositories.core import CoreRepository
from amadeus_bot.repositories.database import CoreDatabase


def make_repository(path: Path) -> CoreRepository:
    database = CoreDatabase(path / "core.sqlite3")
    database.initialize()
    return CoreRepository(database)


def test_members_and_recommendation_pools_are_persistent(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.add_member("10001", "99999")
    assert repository.is_member("10001")

    food_id = repository.add_recommendation("food", "午饭", "咖喱饭", 2, ("米饭",), "10001")
    music_id = repository.add_recommendation("music", "学习", "Song - Artist - URL", 1, (), "10001")

    assert [item.recommendation_id for item in repository.list_recommendations("food")] == [food_id]
    assert [item.recommendation_id for item in repository.list_recommendations("music")] == [music_id]
    assert repository.list_recommendations("activity") == []

    reopened = make_repository(tmp_path)
    assert reopened.is_member("10001")
    assert reopened.get_recommendation(food_id).content == "咖喱饭"


def test_conversation_is_kept_after_repository_reopen(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.append_conversation("group:1", "user", "[100]: hello", "100")
    repository.append_conversation("group:1", "assistant", "hi", None)

    reopened = make_repository(tmp_path)
    assert reopened.recent_conversation("group:1") == [
        {"role": "user", "content": "[100]: hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_ai_quota_counts_successful_calls(tmp_path: Path) -> None:
    repository = make_repository(tmp_path)
    repository.set_ai_quota("chat", 2, "999")
    repository.record_ai_usage(
        task="chat",
        provider="test",
        model="test-model",
        latency_ms=1,
        success=True,
    )
    assert repository.ai_quota_for_task("chat") == (2, 1)
