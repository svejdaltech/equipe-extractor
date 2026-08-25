import json
import os
import secrets
from datetime import datetime, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.calendar_feed import build_ics
from app.checklist import get_checklist_data
from app.database import Base, engine, ensure_column, get_db
from app.parser import UpstreamError, generate_excel, parse_schedule
from app.settings import get_setting, set_setting
from app.sync import sync_meeting

# No public API docs: the app now handles rider PII and an auth-token-protected
# calendar feed, not just the original public schedule export.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
templates = Jinja2Templates(directory="app/templates")

Base.metadata.create_all(bind=engine)
ensure_column("meetings", "end_on", "VARCHAR")

security = HTTPBasic()

try:
    AUTH_USERNAME = os.environ["AUTH_USERNAME"]
    AUTH_PASSWORD = os.environ["AUTH_PASSWORD"]
except KeyError as e:
    raise RuntimeError(f"Missing required environment variable: {e.args[0]}") from e

# Both optional: the calendar feed is disabled (404s) until CALENDAR_TOKEN is set.
# PUBLIC_BASE_URL overrides the request's own host for links inside the feed —
# useful if the app can't reliably see its own public scheme/host behind a proxy.
CALENDAR_TOKEN = os.environ.get("CALENDAR_TOKEN")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

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


def _calendar_urls(request: Request):
    # None (hides the link entirely) when the calendar feed is opt-in but unset —
    # matches /calendar/{token}.ics's own 404-if-unconfigured behaviour.
    if not CALENDAR_TOKEN:
        return None
    base_url = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    https_url = f"{base_url}/calendar/{CALENDAR_TOKEN}.ics"
    # webcal:// signals "subscribe" (not "download once") to compatible calendar
    # apps/OSes, so it's offered as the primary action alongside the plain https
    # link some clients' "add calendar from URL" flows expect to be pasted.
    webcal_url = "webcal://" + https_url.split("://", 1)[1]
    return {"https": https_url, "webcal": webcal_url}


def _export_excel(meeting_id: str, background_tasks: BackgroundTasks, db: Session) -> FileResponse:
    raw_order = get_setting(db, "excel_column_order")
    column_order = [c.strip() for c in raw_order.split(",") if c.strip()] if raw_order else None

    try:
        starts = parse_schedule(meeting_id)
        file_path = generate_excel(starts, column_order=column_order)
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
def home(
    request: Request,
    background_tasks: BackgroundTasks,
    meeting_id: str | None = Query(None, description="Equipe API endpoint — omit to see the bookmarklet page"),
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
):
    """
    With ?meeting_id=<id>: export that meeting's schedule to Excel (unchanged
    behaviour). Without it: show the "Stævne-genvej" bookmarklet page, so it's
    always recoverable on-site if lost from the browser.
    """
    if meeting_id:
        return _export_excel(meeting_id, background_tasks, db)

    base_url = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    return templates.TemplateResponse(request, "home.html", {"base_url": base_url})


@app.get("/meetings/{meeting_id}/export")
def export_meeting(
    meeting_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
):
    """
    Same Excel export as GET /, reachable from the checklist view below.
    """
    return _export_excel(meeting_id, background_tasks, db)


@app.get("/meetings/{meeting_id}/calendar.ics")
def meeting_calendar_ics(meeting_id: int, request: Request, db: Session = Depends(get_db), _auth: None = Depends(require_auth)):
    """
    One-off "add this single event to my calendar" download — unlike the full
    /calendar/{token}.ics subscription feed, this needs no CALENDAR_TOKEN (it's
    a one-time browser download behind the same Basic Auth as everything else,
    not something a calendar app polls unattended).
    """
    meeting = db.get(models.Meeting, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown meeting_id {meeting_id}")

    base_url = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    ics_body = build_ics([meeting], base_url)

    return Response(
        content=ics_body,
        media_type="text/calendar; charset=utf-8",
        # Plain ASCII filename — Content-Disposition needs RFC 5987 filename* encoding
        # for non-ASCII characters, not worth the complexity for an internal filename.
        headers={"Content-Disposition": f'attachment; filename="staevne-{meeting_id}.ics"'},
    )


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
            "calendar_urls": _calendar_urls(request),
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
    has_start_in_meeting = db.execute(
        select(models.Start.id).where(
            models.Start.meeting_id == meeting_id,
            models.Start.rider_id == rider_id,
        )
    ).first()
    if has_start_in_meeting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rider {rider_id} has no start in meeting {meeting_id}",
        )

    now = datetime.now(timezone.utc)
    photographed = db.get(models.Photographed, (meeting_id, rider_id))
    if photographed is None:
        photographed = models.Photographed(meeting_id=meeting_id, rider_id=rider_id, photographed_at=now)
        db.add(photographed)
    else:
        photographed.photographed_at = now
    db.commit()

    return {"rider_id": rider_id, "photographed_at": now.isoformat()}


class SettingsPayload(BaseModel):
    excel_column_order: str = ""


@app.get("/settings", response_class=HTMLResponse)
def settings_page(
    request: Request,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
):
    """
    Small in-app settings page (currently just the Excel export column order),
    so this can be changed on the fly without SSH/.env access mid-event.
    """
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"excel_column_order": get_setting(db, "excel_column_order")},
    )


@app.post("/settings")
def save_settings(
    payload: SettingsPayload,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_auth),
):
    set_setting(db, "excel_column_order", payload.excel_column_order.strip())
    return {"excel_column_order": payload.excel_column_order.strip()}


@app.api_route("/calendar/{token}.ics", methods=["GET", "HEAD"])
def calendar_feed(token: str, request: Request, db: Session = Depends(get_db)):
    """
    Token-protected iCal feed (no Basic Auth — calendar apps generally can't do
    it) with one all-day event per synced meeting, linking back to its checklist.
    Subscribe to this URL directly from Google/Outlook/Apple Calendar.

    Explicitly handles HEAD too — FastAPI/Starlette doesn't add it automatically
    for a GET-only route, and some calendar clients (observed: Thunderbird) send
    a HEAD request first to validate the URL before subscribing. A 405 there was
    enough to make Thunderbird report "could not find calendars at this location"
    even though a plain GET worked fine.
    """
    # compare_digest rejects non-ASCII str arguments outright (TypeError) — compare
    # as UTF-8 bytes instead so a token with any non-ASCII character in the URL
    # (bots/scanners, typos) 404s like any other wrong token instead of 500ing.
    if not CALENDAR_TOKEN or not secrets.compare_digest(token.encode("utf-8"), CALENDAR_TOKEN.encode("utf-8")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if request.method == "HEAD":
        return Response(status_code=200, media_type="text/calendar; charset=utf-8")

    meetings = db.execute(select(models.Meeting)).scalars().all()
    base_url = PUBLIC_BASE_URL or str(request.base_url).rstrip("/")
    ics_body = build_ics(meetings, base_url)

    return Response(content=ics_body, media_type="text/calendar; charset=utf-8")
