import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from amadeus_bot.repositories.group_data import GroupDataRepository
from amadeus_bot.repositories.user_data import UserDataRepository
from amadeus_bot.services import campus, campus_auth
from amadeus_bot.services.analytics import AnalyticsService
from amadeus_bot.services.campus import (
    ActivitySource,
    activity_from_mapping,
    decode_portal_html,
    load_cookie_header_file,
    normalize_activity_payload,
    parse_portal_list,
)
from amadeus_bot.services.courses import CourseService
from amadeus_bot.services.ddl import DDLService
from amadeus_bot.services.jwgl import JwglSource
from amadeus_bot.services.memory import MemoryService

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_wife_pair_is_symmetric_and_quote_is_deduplicated(tmp_path: Path) -> None:
    repository = GroupDataRepository(tmp_path / "groups")
    today = datetime(2026, 8, 28, tzinfo=SHANGHAI).date()
    pair = repository.assign_wife("1", "100", ["200", "300"], today)
    reverse = repository.get_wife("1", pair.partner_id, today)
    assert reverse is not None
    assert reverse.partner_id == "100"

    quote = repository.add_quote("1", "99", "200", "100", "测试", ("有趣",), "原文")
    assert repository.get_quote("1", quote.quote_id) == quote
    with pytest.raises(ValueError, match="已收藏"):
        repository.add_quote("1", "99", "200", "100", "重复", (), "原文")


def test_memory_optout_blocks_new_candidates(tmp_path: Path) -> None:
    service = MemoryService(UserDataRepository(tmp_path / "users"))
    memory_id = service.add_candidate("100", "preference", "喜欢咖啡", confidence=0.9, source_group_id="1")
    assert service.list("100", memory_id)[0].content == "喜欢咖啡"
    service.set_analysis("100", False)
    with pytest.raises(ValueError, match="退出"):
        service.add_candidate("100", "preference", "喜欢茶", confidence=0.9, source_group_id="1")


def test_course_csv_preview_confirm_and_query(tmp_path: Path) -> None:
    service = CourseService(UserDataRepository(tmp_path / "users"))
    content = ("课程名,教师,教室,星期,开始节次,结束节次,周次\n高等数学,张老师,N101,一,1,2,1-16\n").encode()
    preview = service.preview_csv("100", content, "course.csv")
    batch_id, count = service.confirm("100", preview.token)
    assert batch_id and count == 1
    course = service.list("100", 1)[0]
    assert course.name == "高等数学"
    assert course.start_section == 1


def test_campus_parsers_accept_portal_and_activity_shapes() -> None:
    html = (
        '<a href="xntz_content.jsp?urltype=news.NewsContentUrl&amp;wbnewsid=123">校内通知 A</a>'
        "<span>2026-08-28</span>"
    )
    portal = parse_portal_list(html, "http://my.bupt.edu.cn/")
    assert portal[0].item_id == "123"
    assert portal[0].published_at == "2026-08-28"
    activity = normalize_activity_payload({"data": [{"act_id": 7, "act_name": "讲座", "location": "西土城"}]})
    assert activity[0] == activity_from_mapping({"act_id": 7, "act_name": "讲座", "location": "西土城"})


def test_portal_decoder_falls_back_to_gb18030() -> None:
    html = "<title>校内通知-欢迎访问信息服务门户</title>"
    assert decode_portal_html(html.encode("utf-8")) == html
    assert decode_portal_html(html.encode("gb18030")) == html


def test_cookie_header_file_preserves_duplicate_names_and_legacy_json(tmp_path: Path) -> None:
    raw = "JSESSIONID=first; route=node; JSESSIONID=second"
    raw_file = tmp_path / "cookie.txt"
    raw_file.write_text(raw, encoding="utf-8")
    assert load_cookie_header_file(str(raw_file)) == raw

    legacy_file = tmp_path / "cookie.json"
    legacy_file.write_text('{"first": "one", "second": "two"}', encoding="utf-8")
    assert load_cookie_header_file(str(legacy_file)) == "first=one; second=two"


@pytest.mark.asyncio
async def test_jwgl_keepalive_preserves_duplicate_cookie_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = "JSESSIONID=first; route=node; JSESSIONID=second"
    cookie_file = tmp_path / "jwgl-cookie.txt"
    cookie_file.write_text(raw, encoding="utf-8")
    monkeypatch.setenv("AMADEUS_JWGL_COOKIE_FILE", str(cookie_file))

    class FakeResponse:
        url = "https://jwgl.bupt.edu.cn/jsxsd/framework/xsMain_bjyddx.jsp"
        text = "教学一体化服务平台"

        def raise_for_status(self) -> None:
            return None

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def get(self, path: str):
            assert path == JwglSource.HOME_PATH
            return FakeResponse()

    source = JwglSource()
    monkeypatch.setattr(
        source,
        "_client",
        lambda cookie_header: FakeClient() if cookie_header == raw else None,
    )
    await source.keepalive()


@pytest.mark.asyncio
async def test_activity_refresh_accepts_empty_holiday_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "activity-token.txt"
    token_file.write_text("test-token", encoding="utf-8")
    monkeypatch.setenv("AMADEUS_ACTIVITY_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("AMADEUS_ACTIVITY_LIST_ENDPOINT", "/api/v1/participation/admin/act")

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"status": 0, "data": [], "digest": [], "error": None}

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def get(self, endpoint: str, **kwargs):
            assert endpoint == "/api/v1/participation/admin/act"
            assert kwargs["params"] == {"act_state": 0, "page": 1, "page_size": 50}
            assert kwargs["headers"]["Authorization"] == "Bearer test-token"
            return FakeResponse()

    class FakeRepository:
        def set_source_health(self, source: str, **values) -> None:
            assert source == "activity"
            assert values == {"success": True, "item_count": 0}

        def upsert_source_item(self, _source: str, _item: dict) -> bool:
            raise AssertionError("空列表不应写入项目")

        def prune_source_items(self, source: str, item_ids: list[str]) -> int:
            assert source == "activity"
            assert item_ids == []
            return 0

    monkeypatch.setattr(campus.httpx, "AsyncClient", FakeClient)
    assert await ActivitySource(FakeRepository()).refresh() == (0, 0)


@pytest.mark.asyncio
async def test_activity_refresh_renews_expired_token_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "activity-token.txt"
    token_file.write_text("expired-token", encoding="utf-8")
    monkeypatch.setenv("AMADEUS_ACTIVITY_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("AMADEUS_ACTIVITY_LIST_ENDPOINT", "/api/v1/participation/admin/act")
    used_tokens: list[str] = []

    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"status": 0, "data": []}

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def get(self, _endpoint: str, **kwargs):
            token = kwargs["headers"]["Authorization"].removeprefix("Bearer ")
            used_tokens.append(token)
            return FakeResponse(401 if token == "expired-token" else 200)

    class FakeAuthenticator:
        available = True

        async def login_activity(self) -> None:
            token_file.write_text("header.payload.signature", encoding="utf-8")

    class FakeRepository:
        def set_source_health(self, source: str, **values) -> None:
            assert source == "activity"
            assert values == {"success": True, "item_count": 0}

        def upsert_source_item(self, _source: str, _item: dict) -> bool:
            raise AssertionError("空列表不应写入项目")

        def prune_source_items(self, source: str, item_ids: list[str]) -> int:
            assert source == "activity"
            assert item_ids == []
            return 0

    monkeypatch.setattr(campus.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(campus, "CampusAuthenticator", FakeAuthenticator)
    assert await ActivitySource(FakeRepository()).refresh() == (0, 0)
    assert used_tokens == ["expired-token", "header.payload.signature"]


@pytest.mark.asyncio
async def test_activity_login_saves_returned_jwt_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    password_file = tmp_path / "password.txt"
    password_file.write_text("student\nsecret\n", encoding="utf-8")
    token_file = tmp_path / "activity-token.txt"
    monkeypatch.setenv("AMADEUS_PASSWORD_FILE", str(password_file))
    monkeypatch.setenv("AMADEUS_ACTIVITY_TOKEN_FILE", str(token_file))

    class FakeResponse:
        status_code = 200
        headers: dict[str, str] = {}

        def json(self) -> dict:
            return {"data": "header.payload.signature"}

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def post(self, path: str, **kwargs):
            assert path == campus_auth.ACTIVITY_LOGIN_PATH
            assert kwargs["data"] == {
                "username": "student",
                "password": "secret",
                "code": "",
                "captcha": "",
            }
            return FakeResponse()

    monkeypatch.setattr(campus_auth.httpx, "AsyncClient", FakeClient)
    await campus_auth.CampusAuthenticator().login_activity()
    assert token_file.read_text(encoding="utf-8") == "header.payload.signature"
    assert not token_file.with_suffix(".txt.tmp").exists()


@pytest.mark.asyncio
async def test_activity_login_uses_browser_when_site_requires_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    password_file = tmp_path / "password.txt"
    password_file.write_text("student\nsecret\n", encoding="utf-8")
    token_file = tmp_path / "activity-token.txt"
    monkeypatch.setenv("AMADEUS_PASSWORD_FILE", str(password_file))
    monkeypatch.setenv("AMADEUS_ACTIVITY_TOKEN_FILE", str(token_file))

    class FakeResponse:
        status_code = 200
        headers = {"x-real-status": "419"}

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args) -> None:
            return None

        async def post(self, _path: str, **_kwargs):
            return FakeResponse()

    async def fake_browser_login(_self: campus_auth.CampusAuthenticator, account: str, password: str) -> str:
        assert (account, password) == ("student", "secret")
        return "newheader.newpayload.newsignature"

    monkeypatch.setattr(campus_auth.httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        campus_auth.CampusAuthenticator,
        "_login_activity_browser",
        fake_browser_login,
    )
    await campus_auth.CampusAuthenticator().login_activity()
    assert token_file.read_text(encoding="utf-8") == "newheader.newpayload.newsignature"


def test_analytics_counts_deterministic_segments(tmp_path: Path) -> None:
    now = datetime.now().astimezone()
    directory = tmp_path / "logs" / "messages" / "1"
    directory.mkdir(parents=True)
    row = {
        "message_id": "1",
        "direction": "inbound",
        "scene": "group",
        "user_id": "100",
        "group_id": "1",
        "self_id": "999",
        "plain_text": "hello https://example.com",
        "timestamp": int(now.timestamp()),
        "segments": [{"type": "text", "data": {}}, {"type": "image", "data": {}}],
    }
    (directory / f"{now:%Y-%m-%d}.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    window = AnalyticsService(tmp_path / "logs").load_group("1", 1, now=now)
    stats = AnalyticsService.deterministic(window)
    assert stats["messages"] == 1
    assert stats["links"] == 1
    assert stats["segments"]["image"] == 1


def test_ddl_edit_resets_default_reminder_and_due_scan(tmp_path: Path) -> None:
    repository = UserDataRepository(tmp_path / "users")
    service = DDLService(repository)
    now = datetime(2026, 8, 28, 14, 0, tzinfo=SHANGHAI)
    created = service.add("100", "明天15:00", "作业", now=now)
    updated = service.edit(
        "100", created.record.ddl_id, deadline_text="明天16:00", content="数学作业", now=now
    )
    assert updated is not None
    assert updated.content == "数学作业"
    assert updated.reminder_at_utc is not None
