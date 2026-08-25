from datetime import date, datetime, timedelta, timezone


def _escape_text(value: str) -> str:
    # Normalize all newline styles to \n *before* escaping, so a bare \r (e.g. from
    # upstream Equipe data) can't survive as a raw, unescaped carriage return inside
    # a folded content line — lines are joined with \r\n, so a stray CR could be
    # misread as an extra line break by a subscribing calendar app.
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold_line(line: str) -> str:
    # RFC 5545: content lines must be folded at 75 octets, continuation lines
    # start with a single leading space.
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line

    parts = []
    start = 0
    limit = 75
    while start < len(encoded):
        end = min(start + limit, len(encoded))
        # Don't split in the middle of a multi-byte UTF-8 character.
        while end < len(encoded) and (encoded[end] & 0xC0) == 0x80:
            end -= 1
        parts.append(encoded[start:end].decode("utf-8"))
        start = end
        limit = 74  # continuation lines lose one octet to the leading space
    return "\r\n ".join(parts)


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def build_ics(meetings, base_url: str) -> str:
    """Build an RFC 5545 calendar: one all-day VEVENT per meeting, linking back
    to that meeting's checklist page."""
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//equipe-extractor//rytter-tjekliste//DA",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Ridestævner",
    ]

    for meeting in meetings:
        start = _parse_date(meeting.start_on)
        if start is None:
            continue
        end = _parse_date(meeting.end_on) or start
        dtend = end + timedelta(days=1)  # iCal all-day DTEND is exclusive

        url = f"{base_url}/meetings/{meeting.id}"
        summary = meeting.display_name or f"Stævne {meeting.id}"

        lines.append("BEGIN:VEVENT")
        lines.append(_fold_line(f"UID:meeting-{meeting.id}@equipe-extractor"))
        lines.append(f"DTSTAMP:{now}")
        lines.append(f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}")
        lines.append(f"DTEND;VALUE=DATE:{dtend.strftime('%Y%m%d')}")
        lines.append(_fold_line(f"SUMMARY:{_escape_text(summary)}"))
        lines.append(_fold_line(f"URL:{url}"))
        lines.append(_fold_line(f"DESCRIPTION:{_escape_text('Rytter-tjekliste: ' + url)}"))
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
