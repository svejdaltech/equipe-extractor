from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AUTH_USERNAME", "user")
    monkeypatch.setenv("AUTH_PASSWORD", "pass")
    import app.main as main_module
    return TestClient(main_module.app)


def test_export_requires_auth(client):
    r = client.get("/?meeting_id=1")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Basic"


def test_export_rejects_wrong_credentials(client):
    r = client.get("/?meeting_id=1", auth=("user", "wrong"))
    assert r.status_code == 401


def test_export_succeeds_and_cleans_up_temp_file(client, tmp_path):
    fake_file = tmp_path / "out.xlsx"
    fake_file.write_bytes(b"dummy")

    with patch("app.main.parse_schedule", return_value=[{"a": 1}]), \
         patch("app.main.generate_excel", return_value=str(fake_file)):
        r = client.get("/?meeting_id=1", auth=("user", "pass"))

    assert r.status_code == 200
    assert not fake_file.exists()
