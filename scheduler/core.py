"""Deterministic scheduling core: intersect free time across interviewers.

Pure functions, no I/O, no LLM. The agent calls these through tools; the same
logic is what the real Graph-backed implementation will use in Phase 2.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .models import TimeSlot


def _merge(blocks: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for s, e in sorted(blocks):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def _subtract(intervals: list[tuple[datetime, datetime]],
              blocks: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for s, e in intervals:
        cur = s
        for bs, be in _merge(blocks):
            if be <= cur or bs >= e:
                continue
            if bs > cur:
                out.append((cur, min(bs, e)))
            cur = max(cur, be)
            if cur >= e:
                break
        if cur < e:
            out.append((cur, e))
    return out


def find_common_slots(
    busy_map: dict[str, list[tuple[datetime, datetime]]],
    duration_min: int,
    window_start: datetime,
    window_end: datetime,
    tz,
    work_start: int = 9,
    work_end: int = 17,
    buffer_min: int = 15,
    granularity_min: int = 15,
    max_slots: int = 10,
) -> list[TimeSlot]:
    """Return common free slots where *every* attendee is free.

    Rules: weekdays only, inside [work_start, work_end), slot carved at
    granularity_min steps, and a buffer_min gap is kept before the next
    commitment (no buffer needed at the end of the workday).
    """
    duration = timedelta(minutes=duration_min)
    buffer_ = timedelta(minutes=buffer_min)
    step = timedelta(minutes=granularity_min)
    slots: list[TimeSlot] = []

    day = window_start.date()
    last = window_end.date()
    while day <= last and len(slots) < max_slots:
        if day.weekday() < 5:
            day_start = datetime(day.year, day.month, day.day, work_start, tzinfo=tz)
            day_end = datetime(day.year, day.month, day.day, work_end, tzinfo=tz)
            lo, hi = max(day_start, window_start), min(day_end, window_end)
            if hi > lo:
                free = [(lo, hi)]
                for blocks in busy_map.values():
                    clipped = [(max(s, lo), min(e, hi)) for s, e in blocks if e > lo and s < hi]
                    free = _subtract(free, clipped)
                    if not free:
                        break
                for fs, fe in free:
                    effective_end = fe - buffer_ if fe < day_end else fe
                    t = fs
                    while t + duration <= effective_end and len(slots) < max_slots:
                        slots.append(TimeSlot(start=t, end=t + duration))
                        t += step
        day += timedelta(days=1)
    return slots


def rank_slots(slots: list[TimeSlot]) -> list[TimeSlot]:
    """Deterministic ranking: soonest first."""
    return sorted(slots, key=lambda s: s.start)


def format_slot(slot: TimeSlot, viewer_tz: str) -> str:
    """Human-readable slot in the viewer's timezone, e.g. 'Mon Sep 28, 12:00 PM - 12:45 PM CDT'."""
    vzh = ZoneInfo(viewer_tz)
    s = slot.start.astimezone(vzh)
    e = slot.end.astimezone(vzh)
    return f"{s.strftime('%a %b %d, %I:%M %p')} \u2013 {e.strftime('%I:%M %p %Z')}"
