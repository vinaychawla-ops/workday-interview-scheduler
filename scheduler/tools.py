"""ADK function tools for the interview-scheduler agent.

Each tool wraps the mock Workday / Graph backends with JSON-friendly
signatures. In Phase 2 these same tool names get reimplemented against the
real Workday REST/SOAP APIs and Microsoft Graph.

Hard rule: the booking tool (graph_create_interview_event) only runs with a
single-use approval token issued by request_recruiter_approval. No token,
no booking — the approval gate is enforced in code, not just in prompts.
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import date, datetime

from google.adk.tools import FunctionTool

from . import core
from .mock_graph import SEEDED_BUSINESS_DAYS, MockGraph
from .mock_workday import MockWorkday

_workday = MockWorkday()
_graph = MockGraph()
_approval_tokens: set[str] = set()


def reset_mocks(base_date: date | None = None) -> None:
    """Re-seed the mock backends (used by demo.py and tests)."""
    global _workday, _graph
    _workday = MockWorkday()
    _graph = MockGraph(base_date=base_date)
    _approval_tokens.clear()


def _parse_csv(value: str) -> list[str]:
    return [p.strip() for p in value.split(",") if p.strip()]


# ---------------------------------------------------------------- Workday ---
def workday_get_candidate(candidate_id: str) -> dict:
    """Fetch a candidate's profile from Workday by candidate ID."""
    return _workday.get_candidate(candidate_id)


def workday_get_requisition(requisition_id: str) -> dict:
    """Fetch a job requisition (title, round, interview length) from Workday."""
    return _workday.get_requisition(requisition_id)


def workday_get_interview_team(requisition_id: str) -> dict:
    """Fetch the hiring manager and interview panel for a requisition."""
    return _workday.get_interview_team(requisition_id)


# ------------------------------------------------------------------ Graph ---
def graph_get_availability(emails: str, days_ahead: int = 5) -> dict:
    """Return free/busy blocks for comma-separated Outlook emails.

    Args:
        emails: comma-separated attendee email addresses.
        days_ahead: how many business days of seeded calendar to report.
    """
    addrs = _parse_csv(emails)
    busy = _graph.get_busy_blocks(addrs, _graph.window_start, _graph.window_end)
    return {
        email: [{"start": s.isoformat(), "end": e.isoformat()} for s, e in blocks]
        for email, blocks in busy.items()
    }


def scheduler_find_slots(emails: str, duration_minutes: int = 45,
                         max_slots: int = 4,
                         candidate_timezone: str = "America/New_York") -> dict:
    """Find ranked interview slots where every interviewer is free.

    Args:
        emails: comma-separated interviewer email addresses.
        duration_minutes: interview length.
        max_slots: cap on returned slots (soonest first).
        candidate_timezone: used for the candidate-facing display string.
    """
    addrs = _parse_csv(emails)
    busy = _graph.get_busy_blocks(addrs, _graph.window_start, _graph.window_end)
    slots = core.rank_slots(core.find_common_slots(
        busy, duration_minutes, _graph.window_start, _graph.window_end,
        _graph.tz, max_slots=max_slots,
    ))
    if not slots:
        return {"slots": [], "count": 0,
                "note": ("No common availability in the next "
                         f"{SEEDED_BUSINESS_DAYS} business days. "
                         "Widen the window or drop an optional panelist.")}
    recruiter_tz = "America/New_York"
    return {
        "slots": [
            {"index": i,
             "start": s.start.isoformat(), "end": s.end.isoformat(),
             "display_recruiter": core.format_slot(s, recruiter_tz),
             "display_candidate": core.format_slot(s, candidate_timezone)}
            for i, s in enumerate(slots)
        ],
        "count": len(slots),
    }


def request_recruiter_approval(slots_json: str) -> dict:
    """Present ranked slots to the recruiter and capture their decision.

    Args:
        slots_json: JSON array of slot objects from scheduler_find_slots.
    Returns approval dict; on approval includes a single-use approval_token
    that graph_create_interview_event requires.
    """
    slots = json.loads(slots_json)
    auto = os.environ.get("AUTO_APPROVE")
    if auto == "reject":
        return {"approved": False, "reason": "recruiter rejected all proposed slots"}
    if auto is not None and auto != "":
        idx = int(auto)
        chosen = slots[idx]
    else:
        print("\nProposed interview slots (recruiter approval required):")
        for s in slots:
            print(f"  [{s['index']}] {s['display_recruiter']}  "
                  f"(candidate: {s['display_candidate']})")
        choice = input("Approve a slot by number, or 'r' to reject: ").strip().lower()
        if choice == "r":
            return {"approved": False, "reason": "recruiter rejected all proposed slots"}
        idx = int(choice)
        chosen = slots[idx]
    token = "APPR-" + secrets.token_hex(4)
    _approval_tokens.add(token)
    return {"approved": True, "slot_index": idx,
            "start": chosen["start"], "end": chosen["end"],
            "approval_token": token}


def graph_create_interview_event(subject: str, start_iso: str, end_iso: str,
                                 attendee_emails: str, candidate_email: str,
                                 approval_token: str, body: str = "") -> dict:
    """Create the Outlook interview event and send invites.

    REQUIRES a valid single-use approval_token from request_recruiter_approval.
    The candidate is included as an attendee so they receive the invite.
    """
    if approval_token not in _approval_tokens:
        raise PermissionError("recruiter approval required before booking "
                              "(call request_recruiter_approval first)")
    _approval_tokens.discard(approval_token)  # single-use
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    attendees = _parse_csv(attendee_emails)
    if candidate_email not in attendees:
        attendees.append(candidate_email)
    return _graph.create_event(subject, start, end, attendees, candidate_email, body)


def workday_record_interview(candidate_id: str, requisition_id: str,
                             start_iso: str, end_iso: str,
                             interviewer_emails: str, event_id: str) -> dict:
    """Record the booked interview in Workday and move the candidate's stage.

    Only accepts event_ids for events actually created through
    graph_create_interview_event (the approval-gated booking path).
    """
    if not _graph.event_exists(event_id):
        raise ValueError(f"unknown event {event_id}: book via "
                         "graph_create_interview_event first")
    start = datetime.fromisoformat(start_iso)
    end = datetime.fromisoformat(end_iso)
    return _workday.record_interview(candidate_id, requisition_id, start, end,
                                     _parse_csv(interviewer_emails), event_id)


# Introspection helpers (used by demo/tests, not exposed as agent tools).
def get_workday() -> MockWorkday:
    return _workday


def get_graph() -> MockGraph:
    return _graph


TOOLS = [
    FunctionTool(workday_get_candidate),
    FunctionTool(workday_get_requisition),
    FunctionTool(workday_get_interview_team),
    FunctionTool(graph_get_availability),
    FunctionTool(scheduler_find_slots),
    FunctionTool(request_recruiter_approval),
    FunctionTool(graph_create_interview_event),
    FunctionTool(workday_record_interview),
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
