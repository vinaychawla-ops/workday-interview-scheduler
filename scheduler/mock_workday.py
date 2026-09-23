"""In-memory stand-in for the Workday Recruiting API (Phase 1 mock).

Mirrors the real integration surface the agent will need:
  reads  -> candidate profile, requisition, interview team (hiring manager + panel)
  writes -> record a scheduled interview, move the candidate's stage
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from .models import Candidate, Interviewer, Requisition, ScheduledInterview


class MockWorkday:
    def __init__(self) -> None:
        self.interviewers: dict[str, Interviewer] = {
            "I-1": Interviewer("I-1", "Dana Whitfield", "dana.whitfield@acme.example", "hiring_manager"),
            "I-2": Interviewer("I-2", "Ravi Patel", "ravi.patel@acme.example", "panel"),
            "I-3": Interviewer("I-3", "Sofia Marino", "sofia.marino@acme.example", "panel"),
        }
        self.requisitions: dict[str, Requisition] = {
            "R-1001": Requisition(
                "R-1001", "Senior Backend Engineer", "Round 1 \u2014 Technical Screen",
                45, "I-1", ["I-2", "I-3"],
            ),
            "R-1002": Requisition(
                "R-1002", "Product Designer", "Round 1 \u2014 Portfolio Review",
                60, "I-1", ["I-3"],
            ),
        }
        self.candidates: dict[str, Candidate] = {
            "C-501": Candidate("C-501", "Priya Nair", "priya.nair@example.com",
                              "+1-312-555-0148", "America/Chicago"),
            "C-502": Candidate("C-502", "Marcus Lee", "marcus.lee@example.com",
                              "+1-415-555-0192", "America/Los_Angeles"),
        }
        self.interviews: dict[str, ScheduledInterview] = {}
        self._seq = 0

    # ------------------------------------------------------------------ reads
    def get_candidate(self, candidate_id: str) -> dict:
        try:
            return asdict(self.candidates[candidate_id])
        except KeyError:
            raise KeyError(f"unknown candidate {candidate_id}") from None

    def get_requisition(self, requisition_id: str) -> dict:
        try:
            return asdict(self.requisitions[requisition_id])
        except KeyError:
            raise KeyError(f"unknown requisition {requisition_id}") from None

    def get_interview_team(self, requisition_id: str) -> dict:
        req = self.requisitions[requisition_id]
        return {
            "requisition": asdict(req),
            "hiring_manager": asdict(self.interviewers[req.hiring_manager_id]),
            "panel": [asdict(self.interviewers[i]) for i in req.panel_ids],
        }

    # ----------------------------------------------------------------- writes
    def record_interview(self, candidate_id: str, requisition_id: str,
                         start: datetime, end: datetime,
                         interviewer_emails: list[str], event_id: str) -> dict:
        candidate = self.candidates[candidate_id]
        req = self.requisitions[requisition_id]
        self._seq += 1
        interview = ScheduledInterview(
            id=f"IV-{self._seq:04d}",
            candidate_id=candidate_id,
            requisition_id=requisition_id,
            round_name=req.round_name,
            start=start, end=end,
            interviewer_emails=list(interviewer_emails),
            event_id=event_id,
        )
        self.interviews[interview.id] = interview
        candidate.stage = "Interview Scheduled"
        return asdict(interview)
