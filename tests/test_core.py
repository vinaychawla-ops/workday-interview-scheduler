"""Tests for the deterministic scheduling core."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from scheduler import core
from scheduler.models import TimeSlot

ET = ZoneInfo("America/New_York")
# Monday 2026-09-28 (verified: 2026-09-23 is a Wednesday).
BASE = date(2026, 9, 28)


def _busy(email_blocks, day=BASE):
    """Build a busy_map from {email: [(start_hour, end_hour), ...]} for one day."""
    out = {}
    for email, blocks in email_blocks.items():
        out[email] = [
            (datetime(day.year, day.month, day.day, int(s), int((s % 1) * 60), tzinfo=ET),
             datetime(day.year, day.month, day.day, int(e), int((e % 1) * 60), tzinfo=ET))
            for s, e in blocks
        ]
    return out


def _window(day=BASE, days=1):
    start = datetime(day.year, day.month, day.day, 9, tzinfo=ET)
    end = datetime(day.year, day.month, day.day, 17, tzinfo=ET) + timedelta(days=days - 1)
    return start, end


def test_common_window_found():
    busy = _busy({
        "a@x.com": [(9, 10.5), (14, 15.5)],
        "b@x.com": [(10, 12), (16, 17)],
        "c@x.com": [(11.5, 13), (15, 16)],
    })
    ws, we = _window()
    slots = core.find_common_slots(busy, 45, ws, we, ET)
    assert len(slots) == 1
    assert slots[0].start == datetime(2026, 9, 28, 13, 0, tzinfo=ET)
    assert slots[0].end == datetime(2026, 9, 28, 13, 45, tzinfo=ET)


def test_five_weekdays_five_slots_with_seeded_pattern():
    from scheduler.mock_graph import BUSY_PATTERNS, MockGraph
    g = MockGraph(base_date=BASE)
    busy = g.get_busy_blocks(list(BUSY_PATTERNS), g.window_start, g.window_end)
    slots = core.find_common_slots(busy, 45, g.window_start, g.window_end, g.tz)
    assert len(slots) == 5
    assert all(s.start.weekday() < 5 for s in slots)
    assert all(s.start.hour == 13 and s.start.minute == 0 for s in slots)


def test_buffer_blocks_tight_window():
    # 45-min meeting, free window exactly 45 min before next commitment -> no slot
    busy = _busy({"a@x.com": [(9, 13), (13.75, 17)], "b@x.com": [(9, 13), (13.75, 17)]})
    ws, we = _window()
    slots = core.find_common_slots(busy, 45, ws, we, ET, buffer_min=15)
    assert slots == []
    # 60-min window -> exactly one slot (13:00-13:45, buffer to 14:00)
    busy = _busy({"a@x.com": [(9, 13), (14, 17)], "b@x.com": [(9, 13), (14, 17)]})
    slots = core.find_common_slots(busy, 45, ws, we, ET, buffer_min=15)
    assert len(slots) == 1
    assert slots[0].start.hour == 13


def test_no_buffer_needed_at_end_of_workday():
    busy = _busy({"a@x.com": [(9, 16)], "b@x.com": [(9, 16)]})
    ws, we = _window()
    slots = core.find_common_slots(busy, 45, ws, we, ET, buffer_min=15)
    assert len(slots) == 2  # 16:00 and 16:15 at 15-min granularity
    assert slots[0].start == datetime(2026, 9, 28, 16, 0, tzinfo=ET)


def test_weekends_skipped():
    friday = date(2026, 10, 2)  # a Friday
    busy = _busy({"a@x.com": [], "b@x.com": []}, day=friday)
    ws = datetime(2026, 10, 2, 9, tzinfo=ET)
    we = datetime(2026, 10, 5, 17, tzinfo=ET)  # through Monday
    slots = core.find_common_slots(busy, 60, ws, we, ET, max_slots=100)
    days = {s.start.date() for s in slots}
    assert date(2026, 10, 3) not in days  # Saturday
    assert date(2026, 10, 4) not in days  # Sunday
    assert date(2026, 10, 2) in days and date(2026, 10, 5) in days


def test_no_common_availability():
    busy = _busy({"a@x.com": [(9, 17)], "b@x.com": [(9, 12)]})
    ws, we = _window()
    assert core.find_common_slots(busy, 30, ws, we, ET) == []


def test_rank_slots_soonest_first():
    s2 = TimeSlot(datetime(2026, 9, 29, 13, tzinfo=ET), datetime(2026, 9, 29, 13, 45, tzinfo=ET))
    s1 = TimeSlot(datetime(2026, 9, 28, 13, tzinfo=ET), datetime(2026, 9, 28, 13, 45, tzinfo=ET))
    ranked = core.rank_slots([s2, s1])
    assert ranked[0].start.day == 28


def test_format_slot_timezone():
    slot = TimeSlot(datetime(2026, 9, 28, 13, 0, tzinfo=ET),
                    datetime(2026, 9, 28, 13, 45, tzinfo=ET))
    chicago = core.format_slot(slot, "America/Chicago")
    assert "12:00 PM" in chicago and "12:45 PM" in chicago
    assert "CDT" in chicago
