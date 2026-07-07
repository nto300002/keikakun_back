from datetime import date, datetime, timezone
from uuid import UUID

from app.models.calendar_events import CalendarEvent


def _escape_ics_text(value: str | None) -> str:
    if not value:
        return ""
    return (
        value
        .replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _format_ics_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _fold_ics_line(line: str) -> list[str]:
    """RFC 5545 line folding. Keep this byte-aware for Japanese text."""
    max_bytes = 75
    encoded = line.encode("utf-8")
    if len(encoded) <= max_bytes:
        return [line]

    folded: list[str] = []
    current = ""
    current_len = 0
    for char in line:
        char_len = len(char.encode("utf-8"))
        if current and current_len + char_len > max_bytes:
            folded.append(current)
            current = f" {char}"
            current_len = 1 + char_len
        else:
            current += char
            current_len += char_len
    if current:
        folded.append(current)
    return folded


class IcsExportService:
    def build_calendar(self, *, events: list[CalendarEvent]) -> str:
        generated_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Keikakun//Deadline Calendar//JA",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        for event in events:
            lines.extend(self._build_event_lines(event=event, generated_at=generated_at))

        lines.append("END:VCALENDAR")
        folded_lines: list[str] = []
        for line in lines:
            folded_lines.extend(_fold_ics_line(line))
        return "\r\n".join(folded_lines) + "\r\n"

    def _build_event_lines(self, *, event: CalendarEvent, generated_at: str) -> list[str]:
        description_parts = []
        if event.event_description:
            description_parts.append(event.event_description)
        if event.welfare_recipient:
            full_name = " ".join(
                part for part in [event.welfare_recipient.last_name, event.welfare_recipient.first_name] if part
            ).strip()
            if full_name:
                description_parts.append(f"利用者: {full_name}")

        description = "\n".join(description_parts)
        return [
            "BEGIN:VEVENT",
            f"UID:{event.id}@keikakun",
            f"DTSTAMP:{generated_at}",
            f"DTSTART:{_format_ics_datetime(event.event_start_datetime)}",
            f"DTEND:{_format_ics_datetime(event.event_end_datetime)}",
            f"SUMMARY:{_escape_ics_text(event.event_title)}",
            f"DESCRIPTION:{_escape_ics_text(description)}",
            f"CATEGORIES:{_escape_ics_text(event.event_type.value)}",
            "END:VEVENT",
        ]

    def build_filename(self, *, today: date) -> str:
        return f"keikakun-calendar-{today.strftime('%Y%m%d')}.ics"


ics_export_service = IcsExportService()
