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


def test_parse_schedule_caches_repeated_class_section_fetch():
    # Same class_section id referenced from two different meeting_classes must
    # only be fetched once per parse_schedule_from_data() call.
    schedule = {
        "meeting_classes": [
            {"name": "Class A", "start_at": "2025-01-01T09:00:00+00:00", "class_no": 1,
             "class_sections": [{"id": 111, "state": "finished"}]},
            {"name": "Class B", "start_at": "2025-01-01T10:00:00+00:00", "class_no": 2,
             "class_sections": [{"id": 111, "state": "finished"}]},
        ]
    }
    section_response = {"starts": [{"id": 1, "rider_id": 1, "rider_name": "A", "start_at": "2025-01-01T09:05:00+00:00"}]}
    call_count = {"n": 0}

    def fake_get(url, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        call_count["n"] += 1
        resp.json.return_value = section_response
        return resp

    with patch("app.parser.requests.get", side_effect=fake_get):
        rows = parser.parse_schedule_from_data(schedule)

    assert call_count["n"] == 1
    assert len(rows) == 2


def test_generate_excel_puts_preferred_columns_first():
    data = [{"rider_name": "A", "extra_field": "x", "competition_name": "Test"}]

    file_path = parser.generate_excel(data)
    try:
        import pandas as pd
        df = pd.read_excel(file_path)
        assert list(df.columns) == ["competition_name", "rider_name", "extra_field"]
    finally:
        os.remove(file_path)


def test_generate_excel_respects_excel_column_order_env_var(monkeypatch):
    monkeypatch.setenv("EXCEL_COLUMN_ORDER", "horse_name,rider_name")
    data = [{"rider_name": "A", "horse_name": "H", "extra_field": "x", "competition_name": "Test"}]

    file_path = parser.generate_excel(data)
    try:
        import pandas as pd
        df = pd.read_excel(file_path)
        # Custom order first, then any columns not listed, in original order.
        assert list(df.columns) == ["horse_name", "rider_name", "extra_field", "competition_name"]
    finally:
        os.remove(file_path)


def test_generate_excel_sorts_rows_by_start_time():
    data = [
        {"rider_name": "Late", "start_at": "2025-01-01T12:00:00+00:00", "start_no": "5"},
        {"rider_name": "Early", "start_at": "2025-01-01T09:00:00+00:00", "start_no": "1"},
        {"rider_name": "Middle", "start_at": "2025-01-01T10:30:00+00:00", "start_no": "3"},
    ]

    file_path = parser.generate_excel(data)
    try:
        import pandas as pd
        df = pd.read_excel(file_path)
        assert list(df["rider_name"]) == ["Early", "Middle", "Late"]
    finally:
        os.remove(file_path)


def test_generate_excel_sorts_numerically_by_start_no_when_start_at_missing():
    data = [
        {"rider_name": "Ten", "start_no": "10"},
        {"rider_name": "Two", "start_no": "2"},
    ]

    file_path = parser.generate_excel(data)
    try:
        import pandas as pd
        df = pd.read_excel(file_path)
        # Numeric order, not lexicographic ("10" would sort before "2" as strings).
        assert list(df["rider_name"]) == ["Two", "Ten"]
    finally:
        os.remove(file_path)


def test_generate_excel_sorts_alphanumeric_start_no_near_its_numeric_neighbor():
    # Regression test: a plain pd.to_numeric(errors="coerce") turns a jump-off/
    # re-ride bib like "3A" into NaN, which sorts to the very end instead of
    # next to bib 3 where it belongs.
    data = [
        {"rider_name": "Ten", "start_no": "10"},
        {"rider_name": "ThreeA", "start_no": "3A"},
        {"rider_name": "Two", "start_no": "2"},
    ]

    file_path = parser.generate_excel(data)
    try:
        import pandas as pd
        df = pd.read_excel(file_path)
        assert list(df["rider_name"]) == ["Two", "ThreeA", "Ten"]
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
