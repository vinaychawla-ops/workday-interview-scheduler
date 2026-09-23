"""Tool contract tests: serializable outputs, approval gate, agent wiring."""
import json
import os
from datetime import date, datetime

import pytest

from scheduler import tools as T
from scheduler.agent import availability_agent, book_agent, gather_agent, propose_agent, root_agent


@pytest.fixture(autouse=True)
def fresh_mocks(monkeypatch):
    T.reset_mocks(base_date=date(2026, 9, 28))
    monkeypatch.delenv("AUTO_APPROVE", raising=False)
    yield
    monkeypatch.delenv("AUTO_APPROVE", raising=False)


def test_tool_outputs_are_json_serializable():
    team = T.workday_get_interview_team("R-1001")
    emails = ",".join([team["hiring_manager"]["email"]] +
                      [p["email"] for p in team["panel"]])
    payloads = [
        T.workday_get_candidate("C-501"),
        T.workday_get_requisition("R-1001"),
        team,
        T.graph_get_availability(emails),
        T.scheduler_find_slots(emails, candidate_timezone="America/Chicago"),
    ]
    for p in payloads:
        json.dumps(p)  # must not raise


def test_unknown_candidate_raises():
    with pytest.raises(KeyError):
        T.workday_get_candidate("C-999")


def test_approval_token_single_use():
    os.environ["AUTO_APPROVE"] = "0"
    team = T.workday_get_interview_team("R-1001")
    emails = ",".join([team["hiring_manager"]["email"]] +
                      [p["email"] for p in team["panel"]])
    result = T.scheduler_find_slots(emails)
    approval = T.request_recruiter_approval(json.dumps(result["slots"]))
    token = approval["approval_token"]
    slot = result["slots"][0]
    T.graph_create_interview_event("s", slot["start"], slot["end"], emails,
                                   "priya.nair@example.com", token)
    with pytest.raises(PermissionError):
        T.graph_create_interview_event("s", slot["start"], slot["end"], emails,
                                       "priya.nair@example.com", token)


def test_no_slots_note_is_helpful():
    # everyone busy all day, every seeded day -> graceful message, not an exception
    from datetime import timedelta
    graph = T.get_graph()
    for email in graph.calendars:
        blocks = []
        day = graph.window_start.date()
        for _ in range(5):
            blocks.append((
                datetime(day.year, day.month, day.day, 9, tzinfo=graph.tz),
                datetime(day.year, day.month, day.day, 17, tzinfo=graph.tz),
            ))
            day += timedelta(days=1)
        graph.calendars[email] = blocks
    result = T.scheduler_find_slots("dana.whitfield@acme.example")
    assert result["slots"] == [] and "No common availability" in result["note"]


def test_agent_graph_wiring():
    assert [a.name for a in root_agent.sub_agents] == [
        "gather", "availability", "propose", "book"]
    assert gather_agent.tools and availability_agent.tools
    assert propose_agent.tools and book_agent.tools
    # booking tools live ONLY on the book agent (approval-gated stage)
    book_tool_names = {t.name for t in book_agent.tools}
    assert "graph_create_interview_event" in book_tool_names
    assert "workday_record_interview" in book_tool_names
    propose_tool_names = {t.name for t in propose_agent.tools}
    assert "graph_create_interview_event" not in propose_tool_names
    # all eight tools registered
    assert len(T.TOOLS) == 8
