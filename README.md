# Workday Interview Scheduler — Phase-1 Mock Prototype

An agentic app that helps a recruiter schedule candidate interviews:

1. **Gather** — pulls the candidate, requisition, hiring manager, and interview panel from Workday.
2. **Availability** — checks every interviewer's Outlook calendar (free/busy) and finds ranked common slots.
3. **Propose** — presents slots to the recruiter; **nothing is booked without their approval** (human-in-the-loop).
4. **Book** — creates the Outlook/Teams event (candidate gets the invite) and records the interview in Workday, moving the candidate to "Interview Scheduled".

Phase 1 runs entirely on mocks: an in-memory Workday and an in-memory Microsoft Graph. No API keys, no network, no real tenants. Phase 2 swaps the mock backends for the real Workday Recruiting REST/SOAP APIs and Microsoft Graph.

## Quickstart

```bash
cd workday-interview-scheduler
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Interactive walkthrough (you approve the slot at the prompt)
.venv/bin/python demo.py

# Non-interactive: auto-approve slot 0
.venv/bin/python demo.py --auto-approve 0

# Exercise the rejection path (recruiter says no -> nothing booked)
.venv/bin/python demo.py --reject

# Tests
.venv/bin/python -m pytest tests/ -q
```

## Layout

```
scheduler/
  models.py        # Candidate, Interviewer, Requisition, TimeSlot, ScheduledInterview
  mock_workday.py  # in-memory Workday: candidates, reqs, interview teams, stage moves
  mock_graph.py    # in-memory Graph: seeded busy calendars, free/busy, event creation
  core.py          # deterministic slot-finding: intersect free time, buffers, ranking
  tools.py         # ADK FunctionTools wrapping the backends (+ approval-token gate)
  agent.py         # ADK SequentialAgent: gather -> availability -> propose -> book
demo.py            # scripted end-to-end run of the pipeline (no LLM key needed)
tests/             # pytest: core logic, full flow, tool contracts, agent wiring
```

## The approval gate (important)

Booking is gated by a single-use token, enforced **in code**, not just in prompts:

- `request_recruiter_approval(slots)` → on approval, returns `approval_token`.
- `graph_create_interview_event(...)` → raises `PermissionError` without a valid token; the token is consumed on use.
- `workday_record_interview(...)` → only accepts `event_id`s for events created through the gated booking path.

So even a misbehaving LLM step cannot book an interview the recruiter didn't approve.

## Seeded demo data

- Req **R-1001** "Senior Backend Engineer", Round 1 — Technical Screen, 45 min.
- Hiring manager **Dana Whitfield** + panel **Ravi Patel**, **Sofia Marino** (all `@acme.example`).
- Candidate **C-501 Priya Nair** (Chicago) / **C-502 Marcus Lee** (LA).
- Calendars are seeded for the next 5 business days with one shared 60-minute window per day (13:00–14:00 ET) → one 45-min slot per day after the 15-min buffer.

## Running the real ADK agent (needs a Gemini key)

```bash
export GOOGLE_API_KEY=...
.venv/bin/python - <<'EOF'
import asyncio
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from scheduler.agent import root_agent
from scheduler.tools import reset_mocks

async def main():
    reset_mocks()
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, session_service=session_service, app_name="scheduler")
    session = await session_service.create_session(app_name="scheduler", user_id="recruiter")
    async for event in runner.run_async(
        user_id="recruiter", session_id=session.id,
        new_message="Schedule round 1 for candidate C-501 on requisition R-1001"):
        if event.content:
            print(event.content)

asyncio.run(main())
EOF
```

## What's mocked vs. real in Phase 2

| Phase 1 (mock)                  | Phase 2 (real)                                              |
|---------------------------------|-------------------------------------------------------------|
| `MockWorkday`                   | Workday Recruiting REST v4 (`interview.getInterview`, …) + SOAP for interview/schedule ops; OAuth client in the tenant |
| `MockGraph`                     | Microsoft Graph: `getSchedule`/`findMeetingTimes` + `POST /me/events`; Entra ID app registration (delegated permissions first) |
| `request_recruiter_approval` via CLI | Same gate, surfaced in a UI (chat card / web approval)  |
| Deterministic `core.py`         | Unchanged — the slot math doesn't depend on the backend     |
