# AGENTS.md — workday-interview-scheduler

## What this is
Phase-1 mock prototype of the Workday recruiting interview-scheduler agent.
All external systems are in-memory mocks; the scheduling math (`core.py`)
and the approval gate are real and carry over to Phase 2 unchanged.

## Conventions
- **Mocks reset per run**: `scheduler.tools.reset_mocks(base_date=...)` re-seeds
  Workday + Graph. Tests use a fixed Monday (2026-09-28); `demo.py` seeds from today.
- **Datetimes are always timezone-aware** and cross tool boundaries as ISO strings.
  Graph side lives in America/New_York; display converts to the candidate's zone.
- **Approval gate is load-bearing**: `graph_create_interview_event` requires a
  single-use token from `request_recruiter_approval`; the token is consumed on use.
  Never add a booking path that bypasses it. Tests must cover the gate
  (no token -> PermissionError; token reuse -> PermissionError; reject -> nothing booked).
- **Booking tools live only on the `book` ADK agent.** The `propose` agent must
  never receive them — enforced by `test_agent_graph_wiring`.
- **Slot rules** (in `core.find_common_slots`): weekdays, 9–5, 15-min granularity,
  15-min buffer before the next commitment (no buffer at end of workday).
  Change these deliberately; the seeded calendars assume exactly one common
  60-min window/day (13:00–14:00 ET) -> update `BUSY_PATTERNS` expectations in tests if changed.

## ADK notes
- Built against `google-adk` 2.9.2. `SequentialAgent` emits a deprecation warning
  (points at `Workflow`), but `Workflow` can't yet be a sub-agent container for
  this gather→availability→propose→book pipeline, so `SequentialAgent` stays.
- `demo.py` runs the pipeline scripted (no LLM key). The ADK `root_agent` in
  `scheduler/agent.py` needs `GOOGLE_API_KEY`; README shows the Runner snippet.

## Phase 2 checklist (when real tenants exist)
- [ ] Workday: integration system user + OAuth client; map REST v4 reads, SOAP writes
- [ ] Graph: Entra ID app registration, delegated `Calendars.Read`/`Calendars.ReadWrite`
- [ ] Replace `request_recruiter_approval`'s `input()` with a UI approval callback
- [ ] Candidate timezone + locale handling for real candidate data
- [ ] Audit log of every proposal/approval/booking
