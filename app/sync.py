from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import models
from app.parser import get_meeting_info, parse_schedule


def _parse_dt(value):
    # SQLite/SQLAlchemy drops the UTC offset on round-trip but keeps the wall-clock
    # numbers as-is (no conversion) — fine here since Equipe's start_at is already
    # in the event's own local time, and the checklist is read by someone physically
    # at that event, so the browser's local clock matches it directly.
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def sync_meeting(db: Session, meeting_id: str) -> None:
    """Fetch a meeting from Equipe and upsert its riders/starts into the DB."""
    info = get_meeting_info(meeting_id)
    rows = parse_schedule(meeting_id)

    meeting_id_int = int(meeting_id)
    meeting = db.get(models.Meeting, meeting_id_int)
    if meeting is None:
        meeting = models.Meeting(id=meeting_id_int)
        db.add(meeting)
    meeting.display_name = info["display_name"]
    meeting.start_on = info["start_on"]
    meeting.synced_at = datetime.now(timezone.utc)

    for row in rows:
        rider_id = row.get("rider_id")
        start_id = row.get("id")
        if rider_id is None or start_id is None:
            continue

        rider = db.get(models.Rider, rider_id)
        if rider is None:
            rider = models.Rider(id=rider_id)
            db.add(rider)
        rider.name = row.get("rider_name")
        rider.club_name = row.get("club_name")

        start = db.get(models.Start, start_id)
        if start is None:
            start = models.Start(id=start_id)
            db.add(start)
        start.meeting_id = meeting_id_int
        start.rider_id = rider_id
        start.horse_id = row.get("horse_id")
        start.horse_name = row.get("horse_name")
        start.class_section_id = row.get("class_section_id")
        start.class_no = row.get("class_no")
        start.competition_name = row.get("competition_name")
        start.start_no = row.get("start_no")
        start.start_at = _parse_dt(row.get("start_at"))

    db.commit()
