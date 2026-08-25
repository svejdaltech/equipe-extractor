import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app import parser

FIXTURES = Path(__file__).parent.parent / "json"


def _fake_get(schedule, section):
    def fake(url, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = schedule if "schedule" in url else section
        return resp
    return fake


def test_parse_schedule_returns_enriched_rows():
    schedule = json.loads((FIXTURES / "schedule.json").read_text())
    section = json.loads((FIXTURES / "class_section.json").read_text())

    with patch("app.parser.requests.get", side_effect=_fake_get(schedule, section)):
        rows = parser.parse_schedule("69835")

    assert len(rows) == 40
    assert rows[0]["rider_name"]
    assert rows[0]["meeting_id"] == 69835


def test_parse_schedule_rejects_non_numeric_meeting_id():
    with pytest.raises(ValueError):
        parser.parse_schedule("not-a-number")


def test_get_json_raises_on_non_200():
    resp = MagicMock()
    resp.status_code = 404
    resp.text = "not found"
    with patch("app.parser.requests.get", return_value=resp):
        with pytest.raises(parser.UpstreamError):
            parser.get_json("https://example.com")


def test_get_json_wraps_network_errors():
    import requests

    with patch("app.parser.requests.get", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(parser.UpstreamError):
            parser.get_json("https://example.com")


def test_parse_schedule_raises_upstream_error_on_bad_shape():
    with patch("app.parser.requests.get", side_effect=_fake_get({"no_meeting_classes": True}, {})):
        with pytest.raises(parser.UpstreamError):
            parser.parse_schedule("69835")


def test_generate_excel_puts_preferred_columns_first():
    data = [{"rider_name": "A", "extra_field": "x", "competition_name": "Test"}]

    file_path = parser.generate_excel(data)
    try:
        import pandas as pd
        df = pd.read_excel(file_path)
        assert list(df.columns) == ["competition_name", "rider_name", "extra_field"]
    finally:
        os.remove(file_path)


def test_generate_excel_cleans_up_partial_file_on_write_failure():
    data = [{"rider_name": "A"}]

    written_path = {}

    def fake_to_excel(self, filename, index=False):
        written_path["path"] = filename
        Path(filename).write_bytes(b"partial")
        raise OSError("disk full")

    with patch("pandas.DataFrame.to_excel", fake_to_excel):
        with pytest.raises(OSError):
            parser.generate_excel(data)

    assert not os.path.exists(written_path["path"])
