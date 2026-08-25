from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


def _photographed_at_iso(dt):
    # photographed_at is always written as UTC (see main.mark_rider_seen), but SQLite
    # drops the tzinfo on round-trip — reattach it before serializing so the client
    # correctly converts it to the viewer's local time instead of misreading it as
    # already-local (unlike start_at, which genuinely is naive local event time).
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def get_checklist_data(db: Session, meeting_id: int) -> dict:
    """Shape this meeting's starts/riders/photographed rows for the checklist template.

    Mirrors the data shape used by the confirmed UI mockup (riders / starts / seenAt),
    so the client-side sort/filter/status logic can stay unchanged.
    """
    starts = db.execute(
        select(models.Start).where(models.Start.meeting_id == meeting_id)
    ).scalars().all()

    rider_ids = {s.rider_id for s in starts}
    riders_rows = db.execute(
        select(models.Rider).where(models.Rider.id.in_(rider_ids))
    ).scalars().all() if rider_ids else []

    photographed_rows = db.execute(
        select(models.Photographed).where(models.Photographed.meeting_id == meeting_id)
    ).scalars().all()

    riders = {
        str(r.id): {"name": r.name, "club": r.club_name}
        for r in riders_rows
    }

    seen_at = {str(rider_id): None for rider_id in rider_ids}
    for p in photographed_rows:
        # Defensive: only surface photographed rows for riders actually in this
        # meeting's current starts, so a rider who's since scratched (or any other
        # orphaned Photographed row) can't inflate the "X af Y set" count.
        if p.rider_id in rider_ids:
            seen_at[str(p.rider_id)] = _photographed_at_iso(p.photographed_at)

    start_rows = [
        {
            "riderId": str(s.rider_id),
            "horse": s.horse_name,
            "startNo": s.start_no,
            "classNo": s.class_no,
            "className": s.competition_name,
            "startAt": s.start_at.isoformat() if s.start_at else None,
        }
        for s in starts
    ]

    return {"riders": riders, "starts": start_rows, "seenAt": seen_at}
