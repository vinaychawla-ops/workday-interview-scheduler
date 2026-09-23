"""In-memory stand-in for Microsoft Graph calendar APIs (Phase 1 mock).

Mirrors the real calls the agent will need:
  GET /me/calendar/getSchedule  -> busy blocks per attendee (free/busy only)
  POST /me/events               -> create the interview event (sends invites)
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Daily busy blocks per interviewer, as (start_hour, end_hour) in the Graph tz.
# Chosen so the three calendars share exactly one 60-minute common window
# per weekday (13:00-14:00 ET) -> one 45-min slot after the 15-min buffer.
BUSY_PATTERNS: dict[str, list[tuple[float, float]]] = {
    "dana.whitfield@acme.example": [(9, 10.5), (14, 15.5)],
    "ravi.patel@acme.example": [(10, 12), (16, 17)],
    "sofia.marino@acme.example": [(11.5, 13), (15, 16)],
}

SEEDED_BUSINESS_DAYS = 5


class MockGraph:
    def __init__(self, tz: str = "America/New_York", base_date: date | None = None) -> None:
        self.tz = ZoneInfo(tz)
        self.calendars: dict[str, list[tuple[datetime, datetime]]] = {}
        self.sent_invites: list[dict] = []
        self._seq = 0
        base = base_date or date.today()
        first_day: datetime | None = None
        last_day: datetime | None = None
        for email, pattern in BUSY_PATTERNS.items():
            blocks: list[tuple[datetime, datetime]] = []
            day = base
            added = 0
            while added < SEEDED_BUSINESS_DAYS:
                if day.weekday() < 5:  # weekdays only
                    for start_h, end_h in pattern:
                        s = self._at(day, start_h)
                        e = self._at(day, end_h)
                        blocks.append((s, e))
                    if first_day is None:
                        first_day = datetime(day.year, day.month, day.day, 9, tzinfo=self.tz)
                    last_day = datetime(day.year, day.month, day.day, 17, tzinfo=self.tz)
                    added += 1
                day += timedelta(days=1)
            self.calendars[email] = sorted(blocks)
        # Scheduling window the agent may search: first seeded day 09:00 -> last 17:00.
        self.window_start: datetime = first_day  # type: ignore[assignment]
        self.window_end: datetime = last_day  # type: ignore[assignment]

    def _at(self, day: date, hour: float) -> datetime:
        h = int(hour)
        m = int(round((hour - h) * 60))
        return datetime(day.year, day.month, day.day, h, m, tzinfo=self.tz)

    # ------------------------------------------------------------------ reads
    def get_busy_blocks(self, emails: list[str],
                        start: datetime, end: datetime) -> dict[str, list[tuple[datetime, datetime]]]:
        out: dict[str, list[tuple[datetime, datetime]]] = {}
        for email in emails:
            out[email] = [(s, e) for s, e in self.calendars.get(email, [])
                          if e > start and s < end]
        return out

    # ----------------------------------------------------------------- writes
    def create_event(self, subject: str, start: datetime, end: datetime,
                     attendee_emails: list[str], candidate_email: str,
                     body: str = "") -> dict:
        self._seq += 1
        event = {
            "id": f"EVT-{self._seq:04d}",
            "subject": subject,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "attendees": list(attendee_emails),
            "candidate_email": candidate_email,
            "body": body,
            "web_link": f"https://teams.example.com/l/meetup-join/evt-{self._seq:04d}",
        }
        for email in attendee_emails:
            self.calendars.setdefault(email, []).append((start, end))
            self.calendars[email].sort()
        self.sent_invites.append(event)
        return event

    def event_exists(self, event_id: str) -> bool:
        return any(e["id"] == event_id for e in self.sent_invites)
