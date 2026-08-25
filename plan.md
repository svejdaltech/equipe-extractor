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

## P2 — Rider photo-tracking database

Goal: let a photographer at an event see which riders they've already photographed, so they can step away and pick back up later without re-shooting or missing anyone. This needs persistent state per meeting, not just the stateless Excel export.

**Data model** (confirmed against `json/class_section.json` — each start has a stable `rider_id`, `horse_id`, `meeting_id`):
- `riders` — `rider_id` (PK, from Equipe), `rider_name`, `club_name` (last seen values, refreshed on import)
- `starts` — one row per (`meeting_id`, `class_section_id`, `rider_id`, `horse_id`), with `start_no`, `start_at`, `class_no`, `competition_name` — this is what drives the checklist view, since a rider can appear multiple times in one meeting on different horses/classes
- `photographed` — `meeting_id`, `rider_id`, `photographed_at` — deliberately keyed per-meeting-per-rider (not per-start), since "have I shot this person yet today" is usually the question, not "have I shot this specific test". Single photographer confirmed, so no ownership/multi-user column needed. Tapping again just overwrites `photographed_at` with the current time — that's how a rider gets "refreshed" (see below), no separate undo/reset flow needed for now.

**Sync**: reuse `parse_schedule(meeting_id)` to populate/refresh `riders` + `starts` for a meeting instead of only streaming straight to Excel. Add an endpoint (or do it as a side effect of the existing export call) to import a meeting into the DB.

**UI**: per meeting, one "Excel-like" web view (confirmed via `nice to have.md`, folded in here) — a sortable table (click a column header to sort by it, e.g. start time, rider, class), with a tap-to-mark "seen at [time]" action per rider and a "download as Excel" button that produces the same file as `GET /`. The live "time since last seen" readout (`time_now - photographed_at`) sits next to the absolute "set kl. HH:MM" timestamp for each already-marked rider — the elapsed time is what actually matters day-to-day: at a glance the photographer sees who they shot a while ago vs. just now, so they know who's "due" for a re-check after a break. Compute the ticking part client-side (`setInterval` off the server-supplied ISO `photographed_at`) so it updates without a page reload; not-yet-seen riders just show no timestamp. Plain server-rendered HTML (Jinja2 — will need re-adding to `requirements.txt` now that the old auth stack pulled it out) with small vanilla JS for the toggle/ticking/sort is enough; no SPA needed. Sort by start time by default so it doubles as a running order.

**Endpoints** (all behind the same `require_auth` Basic Auth dependency added in P1):
- `GET /meetings/{meeting_id}` — the sortable web view described above
- `POST /meetings/{meeting_id}/riders/{rider_id}/seen` — mark/re-mark seen now (sets `photographed_at = now`)
- `GET /meetings/{meeting_id}/export` — Excel download, same output as today's `GET /`, just reachable from the web view too

**Infra**: SQLite is fine for a single photographer/single instance, but `docker-compose.yml` currently has no volume — the DB file would be lost on every container recreate. Add a named volume for the SQLite file before relying on this for real events.

## P3 — iCal integration (from `nice to have.md`)

Goal (as noted): when a new event/meeting shows up, a calendar entry should appear for it, linking to the prepared page for that event (the P2 web view above).

**Open questions before this can be scoped/built** — flagging rather than guessing:
- How do we learn about a "new event" in the first place? Is there an Equipe endpoint that lists all upcoming meetings we could poll, or is a meeting only known once someone manually enters its `meeting_id` today?
- Who/what "prepares" an event before the calendar entry should fire — is that just "the meeting now exists in our DB" (i.e. automatic once P2's sync has run for it), or a manual step?
- Static `.ics` file, or a live iCal *subscription URL* that calendar apps (Google/Outlook/Apple Calendar) poll periodically? A subscription feed is more useful (updates automatically) but needs a stable, presumably auth-free or token-based URL, since most calendar apps can't do HTTP Basic Auth on a subscribed feed — worth deciding before P1's auth choice becomes a blocker here.

## P4 — Nice to haves

- [ ] Sort output rows by `start_time`/`start_no` in the Excel export, not just column order (original ask in this file).
- [ ] Cache `class_section` lookups within a single export request — right now each section is fetched serially and re-fetched on every export of the same meeting.
- [ ] Restrict/hide `/docs` in production if this ends up handling anything beyond public schedule data.
