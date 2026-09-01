from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from amadeus_bot.services.event_utils import event_group_id, reply_message_id
from amadeus_bot.services.message_log import MessageNormalizer
from amadeus_bot.services.renderer import RenderService


@dataclass
class FakeSegment:
    type: str
    data: dict


class FakeEvent:
    message_type = "group"
    group_id = 123
    message_id = 456
    self_id = 789
    time = 1_700_000_000

    def get_user_id(self) -> str:
        return "100"

    def get_plaintext(self) -> str:
        return "hello"

    def get_message(self):
        return [FakeSegment("text", {"text": "hello"}), FakeSegment("image", {"file": "x"})]


def test_render_cache_key_changes_with_content_and_variant(tmp_path: Path) -> None:
    renderer = RenderService(tmp_path)
    first = renderer.cache_key("hello", kind="plain-text", variant="a")
    assert first == renderer.cache_key("hello", kind="plain-text", variant="a")
    assert first != renderer.cache_key("world", kind="plain-text", variant="a")
    assert first != renderer.cache_key("hello", kind="plain-text", variant="b")


def test_message_normalizer_preserves_segments() -> None:
    record = MessageNormalizer.from_onebot_event(FakeEvent())
    assert record.scene == "group"
    assert record.group_id == "123"
    assert record.plain_text == "hello"
    assert [segment.type for segment in record.segments] == ["text", "image"]


def test_temporary_session_with_group_id_remains_private() -> None:
    event = FakeEvent()
    event.message_type = "private"
    record = MessageNormalizer.from_onebot_event(event)
    assert event_group_id(event) is None
    assert record.scene == "private"
    assert record.group_id is None


def test_reply_message_id_prefers_adapter_reply_metadata() -> None:
    event = FakeEvent()
    event.reply = SimpleNamespace(message_id=987654)
    assert reply_message_id(event) == "987654"


def test_reply_message_id_supports_reply_segment_fallback() -> None:
    event = FakeEvent()
    event.get_message = lambda: [FakeSegment("reply", {"id": "42"})]
    assert reply_message_id(event) == "42"
