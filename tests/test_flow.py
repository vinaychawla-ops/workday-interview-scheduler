"""End-to-end flow tests through the agent tools (mock backends)."""
import json
import os
from datetime import date

import pytest

from scheduler import tools as T

BASE = date(2026, 9, 28)  # Monday


@pytest.fixture(autouse=True)
def fresh_mocks(monkeypatch):
    T.reset_mocks(base_date=BASE)
    monkeypatch.delenv("AUTO_APPROVE", raising=False)
    yield
    monkeypatch.delenv("AUTO_APPROVE", raising=False)


def _book_first_slot():
    team = T.workday_get_interview_team("R-1001")
    candidate = T.workday_get_candidate("C-501")
    interviewers = [team["hiring_manager"]] + team["panel"]
    emails = ",".join(i["email"] for i in interviewers)
    result = T.scheduler_find_slots(emails, duration_minutes=45, max_slots=4,
                                    candidate_timezone=candidate["timezone"])
    assert result["count"] > 0
    os.environ["AUTO_APPROVE"] = "0"
    approval = T.request_recruiter_approval(json.dumps(result["slots"]))
    assert approval["approved"]
    event = T.graph_create_interview_event(
        subject="Round 1 — Technical Screen: Priya Nair — Senior Backend Engineer",
        start_iso=approval["start"], end_iso=approval["end"],
        attendee_emails=emails, candidate_email=candidate["email"],
        approval_token=approval["approval_token"],
    )
    interview = T.workday_record_interview(
        candidate_id="C-501", requisition_id="R-1001",
        start_iso=approval["start"], end_iso=approval["end"],
        interviewer_emails=emails, event_id=event["id"],
    )
    return approval, event, interview, emails, candidate


def test_happy_path_books_everything():
    approval, event, interview, emails, candidate = _book_first_slot()
    graph = T.get_graph()
    # event on every interviewer's calendar + candidate invited
    for email in emails.split(",") + [candidate["email"]]:
        assert email in event["attendees"]
    for email in emails.split(","):
        assert any(b[0].isoformat() == approval["start"]
                   for b in graph.calendars[email])
    # candidate stage moved in Workday
    assert T.workday_get_candidate("C-501")["stage"] == "Interview Scheduled"
    assert interview["event_id"] == event["id"]
    assert interview["status"] == "Scheduled"
    # invite log names the candidate
    assert any(e["id"] == event["id"] and e["candidate_email"] == candidate["email"]
               for e in graph.sent_invites)


def test_reject_books_nothing():
    os.environ["AUTO_APPROVE"] = "reject"
    team = T.workday_get_interview_team("R-1001")
    emails = ",".join([team["hiring_manager"]["email"]] +
                      [p["email"] for p in team["panel"]])
    result = T.scheduler_find_slots(emails, duration_minutes=45)
    approval = T.request_recruiter_approval(json.dumps(result["slots"]))
    assert approval["approved"] is False
    assert T.get_graph().sent_invites == []
    assert T.workday_get_candidate("C-501")["stage"] == "Phone Screen Passed"
    with pytest.raises(PermissionError):
        T.graph_create_interview_event("x", result["slots"][0]["start"],
                                       result["slots"][0]["end"], emails,
                                       "priya.nair@example.com", "bogus-token")


def test_double_booking_prevented():
    approval, event, interview, emails, candidate = _book_first_slot()
    before = T.scheduler_find_slots(emails, duration_minutes=45,
                                    max_slots=10)["slots"]
    starts = [s["start"] for s in before]
    assert approval["start"] not in starts  # booked slot no longer offered


def test_record_rejects_unknown_event():
    with pytest.raises(ValueError, match="unknown event"):
        T.workday_record_interview("C-501", "R-1001",
                                   "2026-09-28T13:00:00-04:00",
                                   "2026-09-28T13:45:00-04:00",
                                   "dana.whitfield@acme.example", "EVT-9999")
