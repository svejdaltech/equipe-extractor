from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.calendar_feed import build_ics
from tests.test_checklist import SAMPLE_MEETING_INFO, SAMPLE_ROWS, patched_sync


def test_build_ics_basic_event():
    meetings = [SimpleNamespace(id=69835, display_name="Forårsstævne", start_on="2025-04-13", end_on="2025-04-13")]
    ics = build_ics(meetings, "https://equipe.svejdaltech.dk")

    assert "BEGIN:VCALENDAR" in ics
    assert "UID:meeting-69835@equipe-extractor" in ics
    assert "DTSTART;VALUE=DATE:20250413" in ics
    assert "DTEND;VALUE=DATE:20250414" in ics
    assert "SUMMARY:Forårsstævne" in ics
    assert "URL:https://equipe.svejdaltech.dk/meetings/69835" in ics
    assert ics.endswith("END:VCALENDAR\r\n")


def test_build_ics_multi_day_event_uses_exclusive_end_date():
    meetings = [SimpleNamespace(id=1, display_name="Sommerstævne", start_on="2025-07-01", end_on="2025-07-03")]
    ics = build_ics(meetings, "https://x")

    assert "DTSTART;VALUE=DATE:20250701" in ics
    assert "DTEND;VALUE=DATE:20250704" in ics


def test_build_ics_escapes_special_characters():
    meetings = [SimpleNamespace(id=1, display_name="Stævne, del 1; test\\slash", start_on="2025-01-01", end_on=None)]
    ics = build_ics(meetings, "https://x")

    assert "Stævne\\, del 1\\; test\\\\slash" in ics


def test_build_ics_skips_meeting_without_start_date():
    meetings = [SimpleNamespace(id=1, display_name="No date", start_on=None, end_on=None)]
    ics = build_ics(meetings, "https://x")

    assert "BEGIN:VEVENT" not in ics


def test_build_ics_folds_long_lines_to_75_octets():
    long_name = "A" * 200
    meetings = [SimpleNamespace(id=1, display_name=long_name, start_on="2025-01-01", end_on=None)]
    ics = build_ics(meetings, "https://x")

    for line in ics.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75


def test_build_ics_normalizes_bare_carriage_return():
    # Regression test: a stray \r (not part of \r\n) left unescaped inside a
    # content line could be misread as an extra line break by a calendar app.
    meetings = [SimpleNamespace(id=1, display_name="Line1\rLine2", start_on="2025-01-01", end_on=None)]
    ics = build_ics(meetings, "https://x")

    assert "SUMMARY:Line1\\nLine2" in ics
    assert all("\r" not in line for line in ics.split("\r\n"))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "user")
    monkeypatch.setenv("AUTH_PASSWORD", "pass")
    import app.main as main_module
    return TestClient(main_module.app)


def test_calendar_feed_404_when_not_configured(client):
    r = client.get("/calendar/anything.ics")
    assert r.status_code == 404


def test_calendar_feed_404_on_wrong_token(client):
    with patch("app.main.CALENDAR_TOKEN", "correct-token"):
        r = client.get("/calendar/wrong-token.ics")
    assert r.status_code == 404


def test_calendar_feed_non_ascii_token_returns_404_not_500(client):
    # Regression test: secrets.compare_digest raises TypeError on non-ASCII str
    # input — a bot/scanner or typo'd URL must still get a clean 404, not a 500.
    with patch("app.main.CALENDAR_TOKEN", "correct-token"):
        r = client.get("/calendar/" + "über.ics")
    assert r.status_code == 404


def test_calendar_feed_head_request_succeeds(client):
    # Regression test: FastAPI/Starlette doesn't add HEAD support automatically
    # for a GET-only route. Some calendar clients (observed: Thunderbird) send a
    # HEAD request to validate the URL before subscribing — a 405 there made
    # Thunderbird report "could not find calendars at this location".
    with patch("app.main.CALENDAR_TOKEN", "correct-token"):
        r = client.head("/calendar/correct-token.ics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")


def test_calendar_feed_head_request_404s_on_wrong_token(client):
    with patch("app.main.CALENDAR_TOKEN", "correct-token"):
        r = client.head("/calendar/wrong-token.ics")
    assert r.status_code == 404


def test_calendar_feed_returns_ics_with_correct_token(client):
    with patched_sync(rows=SAMPLE_ROWS, info=SAMPLE_MEETING_INFO):
        client.get("/meetings/69835", auth=("user", "pass"))

    with patch("app.main.CALENDAR_TOKEN", "correct-token"):
        r = client.get("/calendar/correct-token.ics")

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    assert "meeting-69835@equipe-extractor" in r.text
    assert "Fredensborg-Humlebæk Sportsrideklub" in r.text


def test_calendar_feed_uses_public_base_url_when_set(client):
    with patched_sync(rows=SAMPLE_ROWS, info=SAMPLE_MEETING_INFO):
        client.get("/meetings/69835", auth=("user", "pass"))

    with patch("app.main.CALENDAR_TOKEN", "tok"), patch("app.main.PUBLIC_BASE_URL", "https://equipe.svejdaltech.dk"):
        r = client.get("/calendar/tok.ics")

    assert "https://equipe.svejdaltech.dk/meetings/69835" in r.text
