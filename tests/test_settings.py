import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.settings import get_setting, set_setting


def test_get_setting_returns_default_when_unset():
    db = SessionLocal()
    try:
        assert get_setting(db, "excel_column_order") == ""
        assert get_setting(db, "excel_column_order", "fallback") == "fallback"
    finally:
        db.close()


def test_set_then_get_setting_roundtrips():
    db = SessionLocal()
    try:
        set_setting(db, "excel_column_order", "rider_name,horse_name")
        assert get_setting(db, "excel_column_order") == "rider_name,horse_name"

        # overwriting an existing key updates in place, doesn't duplicate
        set_setting(db, "excel_column_order", "club_name")
        assert get_setting(db, "excel_column_order") == "club_name"
    finally:
        db.close()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "user")
    monkeypatch.setenv("AUTH_PASSWORD", "pass")
    import app.main as main_module
    return TestClient(main_module.app)


def test_settings_page_requires_auth(client):
    r = client.get("/settings")
    assert r.status_code == 401


def test_save_settings_requires_auth(client):
    r = client.post("/settings", json={"excel_column_order": "rider_name"})
    assert r.status_code == 401


def test_save_and_reload_settings(client):
    r = client.post(
        "/settings",
        json={"excel_column_order": "rider_name,horse_name"},
        auth=("user", "pass"),
    )
    assert r.status_code == 200
    assert r.json()["excel_column_order"] == "rider_name,horse_name"

    r = client.get("/settings", auth=("user", "pass"))
    assert r.status_code == 200
    assert 'value="rider_name,horse_name"' in r.text


def test_export_uses_saved_column_order(client):
    from unittest.mock import patch

    client.post(
        "/settings",
        json={"excel_column_order": "horse_name,rider_name"},
        auth=("user", "pass"),
    )

    data = [{"rider_name": "A", "horse_name": "H", "extra_field": "x"}]
    with patch("app.main.parse_schedule", return_value=data):
        r = client.get("/?meeting_id=1", auth=("user", "pass"))

    assert r.status_code == 200

    import io
    import pandas as pd
    df = pd.read_excel(io.BytesIO(r.content))
    assert list(df.columns) == ["horse_name", "rider_name", "extra_field"]
