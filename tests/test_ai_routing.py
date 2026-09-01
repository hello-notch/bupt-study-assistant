from pathlib import Path

from amadeus_bot.adapters.ai_provider import CredentialStore, _parse_tool_call
from amadeus_bot.domain.ai import AITask
from amadeus_bot.services.ai_router import AIRouteCatalog


def test_route_catalog_assigns_cheap_and_quality_models() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "ai_routes.toml"
    catalog = AIRouteCatalog.load(path)

    assert catalog.routes[AITask.PROACTIVE_GATE].primary.model == "deepseek-v4-flash"
    assert catalog.routes[AITask.VISION].primary.model == "deepseek-v4-flash-vision-exp"
    assert catalog.routes[AITask.CHAT].primary.model == "deepseek-v4-flash-vision-exp"
    assert catalog.routes[AITask.CHAT].fallbacks[0].model == "gpt-5.6-terra"


def test_credential_store_parses_pairs_without_copying_file(tmp_path: Path) -> None:
    path = tmp_path / "apikey.txt"
    path.write_text(
        "apikey=test-key-one\nurl=https://one.example\n\napikey: test-key-two\nurl: https://two.example\n",
        encoding="utf-8",
    )
    credentials = CredentialStore.load(path)
    assert set(credentials) == {"one.example", "two.example"}
    assert credentials["one.example"].api_key == "test-key-one"


def test_parse_openai_tool_call() -> None:
    call = _parse_tool_call(
        {
            "id": "call-1",
            "type": "function",
            "function": {"name": "ddl_add", "arguments": '{"deadline":"明天下午三点"}'},
        }
    )
    assert call.call_id == "call-1"
    assert call.name == "ddl_add"
    assert call.arguments == {"deadline": "明天下午三点"}
