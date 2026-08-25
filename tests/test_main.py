import json
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


def test_home_requires_auth(client):
    r = client.get("/")
    assert r.status_code == 401


def test_home_shows_bookmarklet_page_without_meeting_id(client):
    r = client.get("/", auth=("user", "pass"))
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Stævne-genvej" in r.text
    assert "javascript:(function()" in r.text


def test_home_bookmarklet_uses_public_base_url_when_set(client):
    with patch("app.main.PUBLIC_BASE_URL", "https://equipe.svejdaltech.dk"):
        r = client.get("/", auth=("user", "pass"))
    assert "https://equipe.svejdaltech.dk/meetings/" in r.text


def test_home_still_exports_when_meeting_id_given(client):
    with patch("app.main.parse_schedule", return_value=[{"a": 1}]), \
         patch("app.main.generate_excel", return_value=None) as mock_generate:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".xlsx")
        import os
        os.close(fd)
        mock_generate.return_value = path

        r = client.get("/?meeting_id=1", auth=("user", "pass"))

    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]


def test_api_docs_are_disabled(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


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


def test_export_returns_400_on_invalid_meeting_id(client):
    with patch("app.main.parse_schedule", side_effect=ValueError("Invalid meeting_id")):
        r = client.get("/?meeting_id=not-a-number", auth=("user", "pass"))

    assert r.status_code == 400
    assert "Invalid meeting_id" in r.json()["detail"]


def test_export_returns_502_on_upstream_error(client):
    from app.parser import UpstreamError

    with patch("app.main.parse_schedule", side_effect=UpstreamError("Equipe is down")):
        r = client.get("/?meeting_id=1", auth=("user", "pass"))

    assert r.status_code == 502
    assert "Equipe is down" in r.json()["detail"]


def test_embed_json_escapes_script_close_tag():
    # A rider/horse/club name from Equipe containing "</script>" must not be able
    # to break out of the inline <script> block the checklist template embeds it in.
    from app.main import _embed_json

    payload = {"name": "</script><script>alert(1)</script>"}
    result = _embed_json(payload)

    assert "</script>" not in result
    assert json.loads(result.replace("<\\/", "</")) == payload
