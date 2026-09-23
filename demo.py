#!/usr/bin/env python3
"""Scripted end-to-end walkthrough of the Phase-1 mock prototype.

Runs the exact pipeline the ADK agents execute, deterministically and with
no LLM key required:

  1. gather       - candidate + requisition + interview team from mock Workday
  2. availability - free/busy from mock Graph, ranked common slots
  3. propose      - recruiter approves a slot (interactive, --auto-approve N,
                    or --reject to exercise the rejection path)
  4. book         - Outlook event created, interview recorded in Workday

Usage:
  python demo.py                        # interactive approval
  python demo.py --auto-approve 0       # non-interactive, approve first slot
  python demo.py --reject               # recruiter rejects -> nothing booked
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from scheduler import tools as T  # noqa: E402


def step(n: int, title: str) -> None:
    print(f"\n{'=' * 64}\n Step {n}: {title}\n{'=' * 64}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Interview-scheduler Phase-1 demo")
    ap.add_argument("--candidate", default="C-501")
    ap.add_argument("--req", default="R-1001")
    ap.add_argument("--auto-approve", type=int, default=None,
                    help="non-interactive: approve slot index N")
    ap.add_argument("--reject", action="store_true",
                    help="simulate the recruiter rejecting all slots")
    args = ap.parse_args()

    if args.reject:
        os.environ["AUTO_APPROVE"] = "reject"
    elif args.auto_approve is not None:
        os.environ["AUTO_APPROVE"] = str(args.auto_approve)

    T.reset_mocks()  # seed calendars relative to today

    # ---- 1. gather -----------------------------------------------------
    step(1, "Gather from Workday")
    candidate = T.workday_get_candidate(args.candidate)
    team = T.workday_get_interview_team(args.req)
    req = team["requisition"]
    interviewers = [team["hiring_manager"]] + team["panel"]
    emails = [i["email"] for i in interviewers]
    print(f"Candidate : {candidate['name']} <{candidate['email']}> ({candidate['timezone']})")
    print(f"Req       : {req['id']} — {req['title']}")
    print(f"Round     : {req['round_name']} ({req['interview_minutes']} min)")
    print("Team      : " + ", ".join(f"{i['name']} ({i['role']})" for i in interviewers))

    # ---- 2. availability -----------------------------------------------
    step(2, "Check Outlook availability")
    avail = T.graph_get_availability(",".join(emails))
    for email, blocks in avail.items():
        print(f"  {email}: {len(blocks)} busy blocks in window")
    result = T.scheduler_find_slots(
        ",".join(emails),
        duration_minutes=req["interview_minutes"],
        max_slots=4,
        candidate_timezone=candidate["timezone"],
    )
    slots = result["slots"]
    if not slots:
        print("No common availability:", result["note"])
        return 1
    print(f"Found {result['count']} common slots (showing top {len(slots)}):")
    for s in slots:
        print(f"  [{s['index']}] {s['display_recruiter']}  |  candidate: {s['display_candidate']}")

    # ---- 3. propose / approval -------------------------------------------
    step(3, "Recruiter approval (human-in-the-loop)")
    approval = T.request_recruiter_approval(json.dumps(slots))
    if not approval["approved"]:
        print("Recruiter rejected the slots. Nothing was booked — "
              "candidate stage unchanged: "
              f"{T.workday_get_candidate(args.candidate)['stage']!r}.")
        return 0
    print(f"Approved slot {approval['slot_index']}: "
          f"{approval['start']} -> {approval['end']}")

    # ---- 4. book ---------------------------------------------------------
    step(4, "Book the interview")
    subject = f"{req['round_name']}: {candidate['name']} — {req['title']}"
    event = T.graph_create_interview_event(
        subject=subject,
        start_iso=approval["start"],
        end_iso=approval["end"],
        attendee_emails=",".join(emails),
        candidate_email=candidate["email"],
        approval_token=approval["approval_token"],
        body=(f"Interview for {req['title']} ({req['id']}).\n"
              f"Candidate: {candidate['name']} <{candidate['email']}>"),
    )
    interview = T.workday_record_interview(
        candidate_id=args.candidate,
        requisition_id=args.req,
        start_iso=approval["start"],
        end_iso=approval["end"],
        interviewer_emails=",".join(emails),
        event_id=event["id"],
    )

    # ---- verify ----------------------------------------------------------
    step(5, "Verify")
    graph = T.get_graph()
    ok = True
    for email in emails + [candidate["email"]]:
        blocks = graph.calendars.get(email, [])
        on_cal = any(b[0].isoformat() == approval["start"] for b in blocks)
        print(f"  {'OK ' if on_cal else 'MISS'} event on {email}'s calendar")
        ok = ok and on_cal
    stage = T.workday_get_candidate(args.candidate)["stage"]
    print(f"  {'OK ' if stage == 'Interview Scheduled' else 'MISS'} "
          f"Workday stage -> {stage!r}")
    ok = ok and stage == "Interview Scheduled"
    invited = any(e["id"] == event["id"] and e["candidate_email"] == candidate["email"]
                  for e in graph.sent_invites)
    print(f"  {'OK ' if invited else 'MISS'} invite logged for candidate {candidate['email']}")
    ok = ok and invited

    print(f"\nDone. Event {event['id']}: {event['subject']}")
    print(f"Teams link: {event['web_link']}")
    print(f"Workday interview record: {interview['id']} ({interview['status']})")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
