# Equipe Extractor — Plan

## P0 — Bug fixes (parser.py) — done

- [x] `get_json`'s exception handler references `class_section_id`, which is out of scope there — a real fetch failure raises `NameError` instead of the actual error. Fix the error message and remove the dead code after the first `return data` (the status-code branch below it is unreachable).
- [x] Remove the dead `for comp in schedule: ... continue` loop in `parse_schedule` (lines ~47-49) — leftover from debugging, does nothing.
- [x] Add a `timeout=` to every `requests.get` call — right now a slow/hanging Equipe API call hangs the export request forever.
- [x] Check `response.status_code` before calling `.json()` so a non-200 response gives a clear error instead of a JSON-parse exception.
- [x] Validate `meeting_id` (and `class_section_id`) before interpolating into the URL.

## P1 — Cleanup — done

- [x] Auth: replaced the old DB/bcrypt/JWT login stack with HTTP Basic Auth (`app/main.py`), credentials from `AUTH_USERNAME`/`AUTH_PASSWORD` env vars, checked with `secrets.compare_digest`. App fails fast at startup if either var is missing. Deleted the now-unused `models.py`/`database.py` and pruned `sqlalchemy`, `databases`, `bcrypt`, `passlib`, `python-jose`, `itsdangerous`, `jinja2`, `python-multipart` from `requirements.txt`. `docker-compose.yml` now loads `.env` (gitignored) for these; README documents the env vars for local/docker runs.
  - Note: the rider database in P2 will need SQLAlchemy again — that's fine, it's a real dependency for that feature, not leftover cruft.
- [x] Fixed the resource leak in `generate_excel`/`main.py`: `export_to_excel` now registers a `BackgroundTasks.add_task(os.remove, file_path)` so the generated `/tmp/equipe_<uuid>.xlsx` is deleted right after `FileResponse` sends it.
- [x] Replaced `print(...)` debugging with a module logger (`logging.getLogger(__name__)`) in `parser.py`, and dropped the dead/mixed-language debug comments and emoji prints.
- [x] Added `tests/test_parser.py` and `tests/test_main.py` (pytest) covering `parse_schedule` against the real sample JSON in `json/`, `generate_excel`'s column ordering, non-200/invalid-ID error handling, and the Basic Auth flow (missing/wrong/correct credentials, temp-file cleanup). `app/requirements-dev.txt` adds `pytest`/`httpx` on top of the runtime deps. Root `conftest.py` makes `app`/`tests` importable without needing `PYTHONPATH` set manually. All 7 tests pass.

## P2 — Rider photo-tracking database — done

Goal: let a photographer at an event see which riders they've already photographed, so they can step away and pick back up later without re-shooting or missing anyone.

UI design was confirmed via an interactive mockup before building (see memory `project_p2_checklist_ui`) — per-rider not per-start "seen" state, three status states (seen/missed/soon), flat divided list, sort pills, live elapsed-time readout.

- [x] **Data model** (`app/models.py`): `Meeting` (id, display_name, start_on, synced_at), `Rider` (id, name, club_name), `Start` (Equipe's own start `id` as PK, meeting_id, rider_id, horse, class info, start_at), `Photographed` (composite PK `meeting_id`+`rider_id`, `photographed_at`). One table beyond the original 3-table sketch (`Meeting`) — needed to render a page title/date without an extra network round-trip on every request.
- [x] **Sync** (`app/sync.py`): `sync_meeting(db, meeting_id)` upserts riders/starts from `parse_schedule` + the new `parser.get_meeting_info()` helper. Runs on every `GET /meetings/{id}` load, so the checklist always reflects the latest schedule.
- [x] **UI** (`app/templates/checklist.html`): the confirmed mockup ported into a real Jinja2 template — same CSS/JS, data hydrated from the DB instead of hardcoded, "Marker set"/"Marker igen" now POST to the real endpoint and use the server's returned timestamp.
- [x] **Endpoints**, all behind `require_auth`: `GET /meetings/{meeting_id}` (sync + checklist view), `POST /meetings/{meeting_id}/riders/{rider_id}/seen` (mark/re-mark, 404 on unknown rider), `GET /meetings/{meeting_id}/export` (same Excel output as `GET /`, reachable from the checklist's download button).
- [x] **Infra**: `docker-compose.yml` now has a named volume (`equipe-data:/data`) and `DATABASE_URL=sqlite:////data/equipe.db`, so the DB survives container recreation. Local/dev default is `sqlite:///./equipe.db` (gitignored).
- [x] Fixed a timezone round-trip bug found while building this: SQLite drops tzinfo on read-back, so `photographed_at` (always written as UTC) needs its UTC offset reattached before being sent to the client — otherwise the browser would misread it as already-local and show times off by the UTC offset. `start_at` deliberately does *not* get this treatment, since Equipe's times are already the event's own local time and the browser viewing it is physically at that event. Covered by a regression test.
- [x] Tests: `tests/test_checklist.py` covers `sync_meeting` upserts, the checklist page rendering real rider/horse data, mark/re-mark refreshing the timestamp, unknown-rider 404, the `/export` route, and the timezone regression above. 19/19 tests pass across the whole suite.

## P3 — iCal integration — done

Goal (as noted): when a new event/meeting shows up, a calendar entry should appear for it, linking to the prepared page for that event (the P2 web view above).

Resolved the three open questions before building:
- **Discovery**: there's no Equipe "list all meetings" endpoint, so a meeting only becomes known once someone visits it — this now dovetails with the bookmarklet workflow (browse Equipe → click bookmarklet → `/meetings/{id}` syncs it → shows up in the calendar feed on next refresh). No separate "prepare" step.
- **Trigger**: fully automatic — any meeting in the `meetings` table appears in the feed, no manual "add to calendar" action.
- **Auth model**: a live subscription URL secured by a secret token in the path (`/calendar/{token}.ics`), not Basic Auth — confirmed with the user that a public repo doesn't leak the token (it's a runtime secret/env var, never committed, same model as `AUTH_USERNAME`/`AUTH_PASSWORD`). Also confirmed the "connect Gmail/CalDAV and just click add" wish doesn't need real OAuth/CalDAV integration — Google/Outlook/Apple Calendar's built-in "add calendar from URL" already covers it with far less complexity.

- [x] **`app/calendar_feed.py`**: `build_ics(meetings, base_url)` — hand-rolled RFC 5545 builder (no new dependency), one all-day `VEVENT` per meeting with a stable `UID` (so refreshes update rather than duplicate), proper text escaping and 75-octet line folding, `DTEND` computed as the exclusive end date. Verified against the live container with the `icalendar` library that the output round-trips cleanly.
- [x] Added `Meeting.end_on` (was fetched by `parser.get_meeting_info` already but never stored) so multi-day meetings render as a proper date range instead of collapsing to one day.
- [x] **`GET /calendar/{token}.ics`** in `app/main.py` — deliberately *not* behind `require_auth`; instead compares the path token via `secrets.compare_digest` against `CALENDAR_TOKEN` (env var, optional — endpoint 404s if unset, so this is opt-in and doesn't affect existing deployments/tests). Links inside the feed use `PUBLIC_BASE_URL` if set, else fall back to the incoming request's own host (best-effort behind a reverse proxy that doesn't forward scheme headers).
- [x] Documented in `README.md`: generating a token (`openssl rand -hex 32`), the `PUBLIC_BASE_URL` env var, and how to subscribe from Google/Outlook/Apple Calendar.
- [x] Tests: `tests/test_calendar_feed.py` covers `build_ics` (basic event, multi-day exclusive end date, escaping, line folding, skipping meetings with no date) and the route (404 when unconfigured, 404 on wrong token, 200 with correct content and links). 33/33 tests pass across the whole suite.

## P4 — Nice to haves

- [ ] Sort output rows by `start_time`/`start_no` in the Excel export, not just column order (original ask in this file).
- [ ] Cache `class_section` lookups within a single export request — right now each section is fetched serially and re-fetched on every export of the same meeting.
- [ ] Restrict/hide `/docs` in production if this ends up handling anything beyond public schedule data.
