from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.parser import fetch_schedule, get_meeting_info_from_schedule, parse_schedule_from_data


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
    """Fetch a meeting from Equipe and upsert its riders/starts into the DB.

    Also removes any Start rows for this meeting that are no longer present in the
    freshly fetched schedule (e.g. a rider who scratched), so the checklist doesn't
    keep showing withdrawn starts forever.
    """
    schedule = fetch_schedule(meeting_id)
    info = get_meeting_info_from_schedule(schedule)
    rows = parse_schedule_from_data(schedule)

    meeting_id_int = int(meeting_id)
    meeting = db.get(models.Meeting, meeting_id_int)
    if meeting is None:
        meeting = models.Meeting(id=meeting_id_int)
        db.add(meeting)
    meeting.display_name = info["display_name"]
    meeting.start_on = info["start_on"]
    meeting.end_on = info["end_on"]
    meeting.synced_at = datetime.now(timezone.utc)

    # De-duplicate by primary key before touching the DB: a rider commonly appears
    # in several rows (one per class they're starting in), and db.get() inside a
    # single loop doesn't reliably see a not-yet-flushed object added earlier in
    # that same loop — looping straight over `rows` here caused duplicate INSERTs
    # (UNIQUE constraint failures) for any rider with more than one start.
    riders_by_id = {}
    starts_by_id = {}
    for row in rows:
        rider_id = row.get("rider_id")
        start_id = row.get("id")
        if rider_id is None or start_id is None:
            continue

        riders_by_id[rider_id] = {
            "name": row.get("rider_name"),
            "club_name": row.get("club_name"),
        }
        starts_by_id[start_id] = {
            "meeting_id": meeting_id_int,
            "rider_id": rider_id,
            "horse_id": row.get("horse_id"),
            "horse_name": row.get("horse_name"),
            "class_section_id": row.get("class_section_id"),
            "class_no": row.get("class_no"),
            "competition_name": row.get("competition_name"),
            "start_no": row.get("start_no"),
            "start_at": _parse_dt(row.get("start_at")),
        }

    for rider_id, fields in riders_by_id.items():
        rider = db.get(models.Rider, rider_id)
        if rider is None:
            rider = models.Rider(id=rider_id)
            db.add(rider)
        rider.name = fields["name"]
        rider.club_name = fields["club_name"]

    for start_id, fields in starts_by_id.items():
        start = db.get(models.Start, start_id)
        if start is None:
            start = models.Start(id=start_id)
            db.add(start)
        for key, value in fields.items():
            setattr(start, key, value)

    stale_query = select(models.Start).where(models.Start.meeting_id == meeting_id_int)
    if starts_by_id:
        stale_query = stale_query.where(models.Start.id.notin_(starts_by_id.keys()))
    for stale_start in db.execute(stale_query).scalars().all():
        db.delete(stale_start)

    db.commit()
