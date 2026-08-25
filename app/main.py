import json
import os
import secrets
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import models
from app.checklist import get_checklist_data
from app.database import Base, engine, get_db
from app.parser import UpstreamError, generate_excel, parse_schedule
from app.sync import sync_meeting

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

Base.metadata.create_all(bind=engine)

security = HTTPBasic()

try:
    AUTH_USERNAME = os.environ["AUTH_USERNAME"]
    AUTH_PASSWORD = os.environ["AUTH_PASSWORD"]
except KeyError as e:
    raise RuntimeError(f"Missing required environment variable: {e.args[0]}") from e

DANISH_MONTHS = [
    "januar", "februar", "marts", "april", "maj", "juni",
    "juli", "august", "september", "oktober", "november", "december",
]


def require_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, AUTH_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, AUTH_PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


def _format_danish_date(iso_date):
    if not iso_date:
        return None
    try:
        d = datetime.fromisoformat(iso_date)
    except ValueError:
        return iso_date
    return f"{d.day}. {DANISH_MONTHS[d.month - 1]} {d.year}"


def _embed_json(data) -> str:
    # Safe to inline inside a <script> tag: escapes "</" so the data can't close it early.
    return json.dumps(data).replace("</", "<\\/")


def _export_excel(meeting_id: str, background_tasks: BackgroundTasks) -> FileResponse:
    try:
        starts = parse_schedule(meeting_id)
        file_path = generate_excel(starts)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    background_tasks.add_task(os.remove, file_path)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="equipe_" + meeting_id + ".xlsx",
    )


@app.get("/")
def export_to_excel(
    background_tasks: BackgroundTasks,
    meeting_id: str = Query(..., description="Equipe API endpoint"),
    _auth: None = Depends(require_auth),
):
    """
    Export the schedule for a meeting ID to Excel.
    """
    return _export_excel(meeting_id, background_tasks)


@app.get("/meetings/{meeting_id}/export")
def export_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    _auth: None = Depends(require_auth),
):
    """
    Same Excel export as GET /, reachable from the checklist view below.
    """
    return _export_excel(meeting_id, background_tasks)


@app.get("/meetings/{meeting_id}", response_class=HTMLResponse)
def meeting_checklist(
    request: Request,
    meeting_id: str,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
):
    """
    Sync a meeting from Equipe and show the rider photo-tracking checklist for it.
    """
    try:
        sync_meeting(db, meeting_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except UpstreamError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    meeting_id_int = int(meeting_id)
    meeting = db.get(models.Meeting, meeting_id_int)
    data = get_checklist_data(db, meeting_id_int)

    return templates.TemplateResponse(
        request,
        "checklist.html",
        {
            "meeting_id": meeting_id_int,
            "meeting_title": meeting.display_name or f"Stævne {meeting_id_int}",
            "meeting_date": _format_danish_date(meeting.start_on),
            "riders_json": _embed_json(data["riders"]),
            "starts_json": _embed_json(data["starts"]),
            "seen_at_json": _embed_json(data["seenAt"]),
        },
    )


@app.post("/meetings/{meeting_id}/riders/{rider_id}/seen")
def mark_rider_seen(
    meeting_id: int,
    rider_id: int,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
):
    """
    Mark a rider as photographed now. Re-marking just refreshes the timestamp.
    """
    if db.get(models.Rider, rider_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown rider_id {rider_id}")

    now = datetime.now(timezone.utc)
    photographed = db.get(models.Photographed, (meeting_id, rider_id))
    if photographed is None:
        photographed = models.Photographed(meeting_id=meeting_id, rider_id=rider_id, photographed_at=now)
        db.add(photographed)
    else:
        photographed.photographed_at = now
    db.commit()

    return {"rider_id": rider_id, "photographed_at": now.isoformat()}
