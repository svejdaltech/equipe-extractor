import logging

import requests

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10  # seconds


class UpstreamError(Exception):
    """Raised when the Equipe API can't be reached or returns something unusable."""


def _validate_id(value, name):
    if value is None or not str(value).isdigit():
        raise ValueError(f"Invalid {name}: {value!r} (expected a numeric ID)")


def get_json(url):
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.error("Request to %s failed: %s", url, e)
        raise UpstreamError(f"Could not reach {url}: {e}") from e

    if response.status_code != 200:
        logger.error("Request to %s failed with status %s: %s", url, response.status_code, response.text)
        raise UpstreamError(f"Request to {url} failed with status {response.status_code}")

    try:
        return response.json()
    except ValueError as e:
        logger.error("Failed to parse JSON from %s: %s", url, response.text)
        raise UpstreamError(f"Invalid JSON from {url}") from e


def _fetch_schedule(meeting_id):
    _validate_id(meeting_id, "meeting_id")

    meeting_url = f"https://online.equipe.com/api/v1/meetings/{meeting_id}/schedule"
    schedule = get_json(meeting_url)

    # Hvis det er en string ved en fejl (fx JSON i string-format), så prøv at parse det
    if isinstance(schedule, str):
        import json
        try:
            schedule = json.loads(schedule)
        except json.JSONDecodeError:
            raise UpstreamError("Ugyldig JSON returneret fra get_meeting_schedule")

    return schedule


def get_meeting_info(meeting_id):
    schedule = _fetch_schedule(meeting_id)
    return {
        "display_name": schedule.get("display_name") or schedule.get("name"),
        "start_on": schedule.get("start_on"),
        "end_on": schedule.get("end_on"),
    }


def parse_schedule(meeting_id):
    schedule = _fetch_schedule(meeting_id)

    competitions_data = schedule.get("meeting_classes")
    if not isinstance(competitions_data, list):
        raise UpstreamError(f"Uventet format: 'meeting_classes' mangler eller er ikke en liste: {schedule}")

    competitions = []

    for comp in competitions_data:
        comp_info = {
            "competition_name": comp.get("name"),
            "start_time": comp.get("start_at"),
            "class_no": comp.get("class_no"),
        }

        for section in comp.get("class_sections", []):
            class_section_id = section.get("id")
            _validate_id(class_section_id, "class_section_id")

            class_section_url = f"https://online.equipe.com/api/v1/class_sections/{class_section_id}"
            section_details = get_json(class_section_url)

            if section_details and section_details.get("starts"):
                for start in section_details["starts"]:
                    enriched_row = {
                        **comp_info,
                        "class_section_id": class_section_id,
                        "class_section_state": section.get("state"),
                        "placed": section.get("placed"),
                        "results_available": True,
                        **start # <-- her får vi alt rider/hest/points/etc. med
                    }
                    competitions.append(enriched_row)  # tilføj kopi for hver section med resultater

    return competitions


def generate_excel(data: list[dict]) -> str:

    import os
    import uuid

    import pandas as pd

    preferred_columns = [
    "competition_name",
    "start_time",
    "class_no",
    "rider_name",
    "horse_name",
    "club_name",
    "start_no",
    "start_at",
    "result_at",
    "percent",
    "rank",
    "placed",
    "class_section_id",
    "class_section_state",
    ]


    if not data:
        logger.warning("generate_excel called with no data")

    # Convert list of dicts into a DataFrame
    df = pd.DataFrame(data)

    # Rearrange columns: preferred ones first, then the rest
    preferred = [col for col in preferred_columns if col in df.columns]
    others = [col for col in df.columns if col not in preferred]
    df = df[preferred + others]

    # Optionally, expand 'points' array to separate columns
    if "points" in df.columns and not df["points"].isnull().all():
        points_df = df["points"].apply(pd.Series)
        points_df.columns = [f"point_{i+1}" for i in points_df.columns]
        df = pd.concat([df.drop(columns=["points"]), points_df], axis=1)

    # Generate filename
    filename = f"/tmp/equipe_{uuid.uuid4()}.xlsx"

    # Export to Excel
    try:
        df.to_excel(filename, index=False)
    except Exception:
        if os.path.exists(filename):
            os.remove(filename)
        raise

    return filename