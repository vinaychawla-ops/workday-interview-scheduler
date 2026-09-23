"""Shared data models for the interview-scheduler prototype."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Candidate:
    id: str
    name: str
    email: str
    phone: str
    timezone: str
    stage: str = "Phone Screen Passed"


@dataclass
class Interviewer:
    id: str
    name: str
    email: str
    role: str  # "hiring_manager" | "panel"


@dataclass
class Requisition:
    id: str
    title: str
    round_name: str
    interview_minutes: int
    hiring_manager_id: str
    panel_ids: list[str] = field(default_factory=list)


@dataclass
class TimeSlot:
    start: datetime  # timezone-aware
    end: datetime

    def to_dict(self) -> dict:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


@dataclass
class ScheduledInterview:
    id: str
    candidate_id: str
    requisition_id: str
    round_name: str
    start: datetime
    end: datetime
    interviewer_emails: list[str]
    event_id: str
    status: str = "Scheduled"
