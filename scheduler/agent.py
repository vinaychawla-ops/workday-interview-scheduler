"""ADK agent definitions for the interview scheduler.

Pipeline (SequentialAgent):
  gather       -> pull candidate + requisition + interview team from Workday
  availability -> free/busy via Graph, then ranked common slots
  propose      -> present slots, get recruiter approval (human-in-the-loop)
  book         -> create the Outlook event, record the interview in Workday

Run with a Gemini key:
  export GOOGLE_API_KEY=...   (or GEMINI_API_KEY)
  python -m scheduler.run_agent "Schedule round 1 for candidate C-501 on requisition R-1001"
"""
from __future__ import annotations

from google.adk.agents import LlmAgent, SequentialAgent

from .tools import TOOLS_BY_NAME

MODEL = "gemini-2.5-flash"

gather_agent = LlmAgent(
    name="gather",
    model=MODEL,
    description="Pulls candidate, requisition, and interview-team data from Workday.",
    instruction=(
        "You are the intake step of an interview-scheduling pipeline. "
        "The recruiter's request names a candidate ID and a requisition ID. "
        "Call workday_get_candidate, workday_get_requisition, and "
        "workday_get_interview_team, then output a compact JSON summary with: "
        "candidate (id, name, email, timezone), requisition (id, title, round_name, "
        "interview_minutes), and interviewers (list of {name, email, role}). "
        "Output ONLY the JSON summary."
    ),
    tools=[TOOLS_BY_NAME["workday_get_candidate"],
           TOOLS_BY_NAME["workday_get_requisition"],
           TOOLS_BY_NAME["workday_get_interview_team"]],
)

availability_agent = LlmAgent(
    name="availability",
    model=MODEL,
    description="Finds common free slots across interviewers' Outlook calendars.",
    instruction=(
        "You receive the JSON summary from the gather step. "
        "Call graph_get_availability with the comma-separated interviewer emails, "
        "then scheduler_find_slots with the same emails, the interview_minutes as "
        "duration_minutes, and the candidate's timezone as candidate_timezone. "
        "If no slots come back, report that clearly and suggest widening the "
        "window or dropping an optional panelist. Otherwise output the slots "
        "JSON array unchanged for the next step."
    ),
    tools=[TOOLS_BY_NAME["graph_get_availability"],
           TOOLS_BY_NAME["scheduler_find_slots"]],
)

propose_agent = LlmAgent(
    name="propose",
    model=MODEL,
    description="Presents ranked slots and captures the recruiter's approval.",
    instruction=(
        "You receive the ranked slots JSON array. Present each slot with its "
        "display_recruiter and display_candidate times, then call "
        "request_recruiter_approval with the slots JSON array as slots_json. "
        "If the recruiter rejects, output the rejection and STOP — do not book "
        "anything. If approved, output the approval result (slot_index, start, "
        "end, approval_token) as JSON."
    ),
    tools=[TOOLS_BY_NAME["request_recruiter_approval"]],
)

book_agent = LlmAgent(
    name="book",
    model=MODEL,
    description="Books the approved slot and records it in Workday.",
    instruction=(
        "You receive the approval result from the propose step. "
        "If approved is false, do nothing and summarize the outcome. "
        "If approved is true: "
        "1) call graph_create_interview_event with subject "
        "'<round_name>: <candidate name> - <req title>', the approved start/end, "
        "all interviewer emails as attendee_emails, the candidate's email as "
        "candidate_email, and the approval_token. "
        "2) call workday_record_interview with candidate_id, requisition_id, "
        "start/end, interviewer emails, and the returned event id. "
        "Then summarize: when, who, the Teams link, and the candidate's new "
        "Workday stage."
    ),
    tools=[TOOLS_BY_NAME["graph_create_interview_event"],
           TOOLS_BY_NAME["workday_record_interview"]],
)

root_agent = SequentialAgent(
    name="interview_scheduler",
    description="Schedules candidate interviews: Workday lookup, Outlook "
                "availability, recruiter approval, booking.",
    sub_agents=[gather_agent, availability_agent, propose_agent, book_agent],
)
