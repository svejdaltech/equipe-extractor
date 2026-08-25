import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal

SAMPLE_ROWS = [
    {
        "competition_name": "LD sløjfedressur Hest",
        "start_time": "2025-04-13T08:30:00+02:00",
        "class_no": 1,
        "class_section_id": 1071479,
        "class_section_state": "finished",
        "placed": True,
        "results_available": True,
        "rider_id": 5627476,
        "horse_id": 6770414,
        "club_id": 1709426,
        "id": 17949729,
        "rider_name": "Rigmor Gabrielle Kousted Jessen",
        "horse_name": "AMADEUS",
        "club_name": "Fredensborg-Humlebæk Sportsrideklub",
        "start_no": "3",
        "start_at": "2025-04-13T08:40:00+02:00",
        "meeting_id": 69835,
    }
]

SAMPLE_MEETING_INFO = {
    "display_name": "Fredensborg-Humlebæk Sportsrideklub",
    "start_on": "2025-04-13",
    "end_on": "2025-04-13",
}

# Same rider, two starts (different class/horse) — this is the normal case that
# crashed sync_meeting in production with a UNIQUE constraint failure on riders.id.
MULTI_START_RIDER_ROWS = [
    {**SAMPLE_ROWS[0], "id": 17949729, "class_no": 1, "start_no": "3"},
    {**SAMPLE_ROWS[0], "id": 17949730, "class_no": 3, "start_no": "2", "horse_name": "Cassidy"},
]


@contextmanager
def patched_sync(rows=SAMPLE_ROWS, info=SAMPLE_MEETING_INFO):
    """Bypass the network entirely: fetch_schedule's return value is irrelevant
    since both consumers below (get_meeting_info_from_schedule / parse_schedule_from_data)
    are mocked directly, matching the boundary sync_meeting() actually calls."""
    with patch("app.sync.fetch_schedule", return_value={}), \
         patch("app.sync.get_meeting_info_from_schedule", return_value=info), \
         patch("app.sync.parse_schedule_from_data", return_value=rows):
        yield


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "user")
    monkeypatch.setenv("AUTH_PASSWORD", "pass")
    import app.main as main_module
    return TestClient(main_module.app)


def test_sync_meeting_upserts_rows():
    from app.sync import sync_meeting

    db = SessionLocal()
    try:
        with patched_sync():
            sync_meeting(db, "69835")

        meeting = db.get(models.Meeting, 69835)
        assert meeting.display_name == "Fredensborg-Humlebæk Sportsrideklub"

        rider = db.get(models.Rider, 5627476)
        assert rider.name == "Rigmor Gabrielle Kousted Jessen"

        start = db.get(models.Start, 17949729)
        assert start.meeting_id == 69835
        assert start.horse_name == "AMADEUS"
    finally:
        db.close()


def test_sync_meeting_handles_rider_with_multiple_starts():
    # Regression test: syncing a rider who appears in more than one start used to
    # raise sqlalchemy.exc.IntegrityError (UNIQUE constraint failed: riders.id).
    from app.sync import sync_meeting

    db = SessionLocal()
    try:
        with patched_sync(rows=MULTI_START_RIDER_ROWS):
            sync_meeting(db, "69835")

        rider = db.get(models.Rider, 5627476)
        assert rider.name == "Rigmor Gabrielle Kousted Jessen"

        assert db.get(models.Start, 17949729) is not None
        assert db.get(models.Start, 17949730).horse_name == "Cassidy"
    finally:
        db.close()


def test_checklist_shows_prior_seen_from_other_meeting():
    from app.checklist import get_checklist_data
    from app.sync import sync_meeting

    db = SessionLocal()
    try:
        with patched_sync(rows=SAMPLE_ROWS):
            sync_meeting(db, "69835")
        db.add(models.Photographed(
            meeting_id=69835,
            rider_id=5627476,
            photographed_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        ))
        db.commit()

        other_meeting_rows = [{**SAMPLE_ROWS[0], "id": 99999999, "meeting_id": 70000}]
        with patched_sync(rows=other_meeting_rows):
            sync_meeting(db, "70000")

        data = get_checklist_data(db, 70000)
        assert data["riders"]["5627476"]["lastSeenBefore"].startswith("2025-06-01")

        # Meeting 69835's own view has no *other*-meeting history to show yet.
        data_a = get_checklist_data(db, 69835)
        assert data_a["riders"]["5627476"]["lastSeenBefore"] is None
    finally:
        db.close()


def test_sync_meeting_removes_stale_starts():
    from app.sync import sync_meeting

    db = SessionLocal()
    try:
        with patched_sync(rows=SAMPLE_ROWS):
            sync_meeting(db, "69835")
        assert db.get(models.Start, 17949729) is not None

        # Rider scratched / class removed: next sync no longer sees this start.
        with patched_sync(rows=[]):
            sync_meeting(db, "69835")
        assert db.get(models.Start, 17949729) is None
    finally:
        db.close()


def test_checklist_requires_auth(client):
    r = client.get("/meetings/69835")
    assert r.status_code == 401


def test_checklist_renders_riders(client):
    with patched_sync():
        r = client.get("/meetings/69835", auth=("user", "pass"))

    assert r.status_code == 200
    assert "Rigmor Gabrielle Kousted Jessen" in r.text
    assert "AMADEUS" in r.text


def test_mark_seen_then_remark_refreshes_timestamp(client):
    with patched_sync():
        client.get("/meetings/69835", auth=("user", "pass"))

    r1 = client.post("/meetings/69835/riders/5627476/seen", auth=("user", "pass"))
    assert r1.status_code == 200
    first_ts = r1.json()["photographed_at"]

    r2 = client.post("/meetings/69835/riders/5627476/seen", auth=("user", "pass"))
    assert r2.status_code == 200
    second_ts = r2.json()["photographed_at"]

    assert second_ts >= first_ts


def test_mark_seen_rejects_rider_not_in_this_meeting(client):
    # Rider exists (synced via meeting 69835), but has no start in meeting 12345 —
    # marking them seen there must not be allowed to create a cross-meeting record.
    with patched_sync():
        client.get("/meetings/69835", auth=("user", "pass"))

    r = client.post("/meetings/12345/riders/5627476/seen", auth=("user", "pass"))
    assert r.status_code == 404


def test_checklist_reload_serves_timezone_aware_seen_at(client):
    # Regression test: SQLite drops tzinfo on round-trip, so a naively-reserialized
    # photographed_at would make the browser misread a UTC timestamp as local time.
    with patched_sync():
        client.get("/meetings/69835", auth=("user", "pass"))

    client.post("/meetings/69835/riders/5627476/seen", auth=("user", "pass"))

    with patched_sync():
        r = client.get("/meetings/69835", auth=("user", "pass"))

    assert r.status_code == 200
    match = re.search(r'var seenAt = ({.*?});', r.text)
    assert match, "seenAt assignment not found in rendered page"
    seen_at = json.loads(match.group(1))
    assert seen_at["5627476"].endswith("+00:00")


def test_mark_seen_unknown_rider_returns_404(client):
    r = client.post("/meetings/69835/riders/999999/seen", auth=("user", "pass"))
    assert r.status_code == 404


def test_export_via_meeting_route(client):
    with patch("app.main.parse_schedule", return_value=[{"a": 1}]), \
         patch("app.main.generate_excel") as mock_generate:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        import os
        os.close(fd)
        mock_generate.return_value = path

        r = client.get("/meetings/69835/export", auth=("user", "pass"))

    assert r.status_code == 200
