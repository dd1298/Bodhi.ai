"""Student-facing endpoints: shared textbooks, mock test lifecycle.

A mock test is a one-shot, time-boxed paper attempt:
    1. POST /api/student/mock-tests           -> generate (kicks off paper LLM)
    2. GET  /api/student/mock-tests           -> list mine
    3. GET  /api/student/mock-tests/:id       -> fetch (correct_options hidden if not submitted)
    4. POST /api/student/mock-tests/:id/start -> set started_at + ends_at
    5. PATCH /api/student/mock-tests/:id/answers -> autosave answers
    6. POST /api/student/mock-tests/:id/submit -> finalize + auto-grade
    7. GET  /api/student/mock-tests/:id/result -> graded result with correct answers

Mock tests reuse the existing paper-generation background worker so we get
the same robust LLM retry + provider fallback for free.
"""
from __future__ import annotations

import asyncio as _asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from deps import api_router, db, logger, utcnow_iso
from workers import generate_paper_background


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _require_student(user: dict) -> None:
    if user.get("role") not in ("student", "admin"):
        raise HTTPException(status_code=403, detail="Student access required")


def _strip_secrets(paper: dict) -> dict:
    """Hide correct_option + diagram_description (sometimes leaks the answer)
    while a mock test is in progress."""
    out = {**paper}
    sections = []
    for s in paper.get("sections") or []:
        qs = []
        for q in s.get("questions") or []:
            sq = {k: v for k, v in q.items() if k not in ("correct_option", "diagram_description")}
            qs.append(sq)
        sections.append({**s, "questions": qs})
    out["sections"] = sections
    return out


def _parse_iso(s: str | None):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class MockTestCreate(BaseModel):
    textbook_ids: list[str] = Field(..., min_length=1)
    topics: list[str] = Field(..., min_length=1)
    subject: str = ""
    class_name: str = ""
    difficulty: str = "medium"  # easy | medium | hard
    question_count: int = Field(10, ge=3, le=40)
    duration_minutes: int = Field(20, ge=5, le=180)


class AnswerInput(BaseModel):
    question_id: str
    selected_option: Optional[int] = None
    text_answer: Optional[str] = None


class AnswersPatch(BaseModel):
    answers: list[AnswerInput]


# ---------------------------------------------------------------------------
# Shared library — what textbooks can a student practise from?
# ---------------------------------------------------------------------------
@api_router.get("/student/textbooks")
async def student_textbooks(user: dict = Depends(get_current_user)):
    _require_student(user)
    docs = (
        await db.textbooks.find(
            {
                "is_deleted": False,
                "is_shared": True,
                "status": {"$in": ["indexed", "topics_ready"]},
            },
            {"_id": 0, "id": 1, "subject": 1, "class_name": 1, "original_filename": 1, "topics": 1},
        )
        .sort("created_at", -1)
        .to_list(200)
    )
    return docs


# ---------------------------------------------------------------------------
# Create a mock test
# ---------------------------------------------------------------------------
@api_router.post("/student/mock-tests")
async def create_mock_test(req: MockTestCreate, user: dict = Depends(get_current_user)):
    _require_student(user)

    # Resolve textbooks — students can only use SHARED books.
    textbooks: list = []
    for tid in req.textbook_ids:
        tb = await db.textbooks.find_one(
            {"id": tid, "is_deleted": False, "is_shared": True}, {"_id": 0}
        )
        if not tb:
            raise HTTPException(
                status_code=404, detail=f"Shared textbook {tid} not available"
            )
        textbooks.append(tb)

    merged_chunks: list = []
    max_per = max(2, 8 // max(1, len(textbooks)))
    for tb in textbooks:
        merged_chunks.extend((tb.get("chunks") or [])[:max_per])
    context_excerpt = "\n\n".join(merged_chunks)[:10000]

    topics_weighted = [{"name": t.strip(), "weight": 5} for t in req.topics if t.strip()]
    if not topics_weighted:
        raise HTTPException(status_code=400, detail="At least one topic required")

    subject = req.subject or textbooks[0].get("subject", "")
    klass = req.class_name or textbooks[0].get("class_name", "")
    total_marks = req.question_count  # 1 mark per MCQ

    paper_id = str(uuid.uuid4())
    paper_doc = {
        "id": paper_id,
        "owner_id": user["id"],
        "title": f"Mock Test — {subject or 'Practice'}",
        "subject": subject,
        "class_name": klass,
        "textbook_id": req.textbook_ids[0],
        "textbook_ids": req.textbook_ids,
        "topics": topics_weighted,
        "difficulty": req.difficulty,
        "duration_minutes": req.duration_minutes,
        "total_marks": total_marks,
        "distribution": {"information": 40, "concept": 40, "application": 20},
        "format_distribution": {"mcq": 100},
        "custom_instructions": "",
        "section_blueprint": "",
        "instructions": "",
        "sections": [],
        "diagrams_pending": 0,
        "generation_status": "pending",
        "generation_error": None,
        "is_mock_test": True,
        "created_at": utcnow_iso(),
        "is_deleted": False,
    }
    await db.papers.insert_one(paper_doc)

    test_id = str(uuid.uuid4())
    test_doc = {
        "id": test_id,
        "student_id": user["id"],
        "paper_id": paper_id,
        "status": "not_started",
        "duration_minutes": req.duration_minutes,
        "question_count": req.question_count,
        "started_at": None,
        "ends_at": None,
        "submitted_at": None,
        "answers": {},
        "score": None,
        "created_at": utcnow_iso(),
    }
    await db.mock_tests.insert_one(test_doc)

    _asyncio.create_task(
        generate_paper_background(
            paper_id=paper_id,
            owner_id=user["id"],
            subject=subject,
            klass=klass,
            topics_weighted=topics_weighted,
            difficulty=req.difficulty,
            distribution={"information": 40, "concept": 40, "application": 20},
            total_marks=total_marks,
            duration_minutes=req.duration_minutes,
            context_excerpt=context_excerpt,
            feedback_hints="",
            format_distribution={"mcq": 100},
            custom_instructions="",
            section_blueprint="",
        )
    )

    return {"id": test_id, "paper_id": paper_id, "status": "not_started"}


# ---------------------------------------------------------------------------
# List + fetch
# ---------------------------------------------------------------------------
@api_router.get("/student/mock-tests")
async def list_mock_tests(user: dict = Depends(get_current_user)):
    _require_student(user)
    rows = (
        await db.mock_tests.find({"student_id": user["id"]}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(100)
    )
    # Attach lightweight paper meta.
    out = []
    for r in rows:
        paper = await db.papers.find_one(
            {"id": r["paper_id"]},
            {"_id": 0, "title": 1, "subject": 1, "class_name": 1, "generation_status": 1},
        )
        if paper:
            r["paper"] = paper
        out.append(r)
    return out


@api_router.get("/student/mock-tests/{test_id}")
async def get_mock_test(test_id: str, user: dict = Depends(get_current_user)):
    _require_student(user)
    t = await db.mock_tests.find_one({"id": test_id}, {"_id": 0})
    if not t or t["student_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Mock test not found")
    paper = await db.papers.find_one({"id": t["paper_id"]}, {"_id": 0})
    if paper:
        # Auto-expire if timer ran out without an explicit submit.
        if t["status"] == "in_progress":
            ends = _parse_iso(t.get("ends_at"))
            if ends and datetime.now(timezone.utc) > ends:
                t["status"] = "expired"
                await db.mock_tests.update_one(
                    {"id": test_id},
                    {"$set": {"status": "expired"}},
                )
        # Hide correct options until submitted/expired.
        if t["status"] not in ("submitted", "expired"):
            paper = _strip_secrets(paper)
        t["paper"] = paper
    return t


# ---------------------------------------------------------------------------
# Start the timer
# ---------------------------------------------------------------------------
@api_router.post("/student/mock-tests/{test_id}/start")
async def start_mock_test(test_id: str, user: dict = Depends(get_current_user)):
    _require_student(user)
    t = await db.mock_tests.find_one({"id": test_id}, {"_id": 0})
    if not t or t["student_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Mock test not found")
    paper = await db.papers.find_one({"id": t["paper_id"]}, {"_id": 0, "generation_status": 1})
    if not paper or paper.get("generation_status") != "ready":
        raise HTTPException(
            status_code=409,
            detail="Paper is still being generated. Please wait a few seconds.",
        )
    if t["status"] == "submitted":
        raise HTTPException(status_code=409, detail="Mock test already submitted")
    if t["status"] == "in_progress":
        return t  # idempotent

    now = datetime.now(timezone.utc)
    ends_at = now + timedelta(minutes=t["duration_minutes"])
    await db.mock_tests.update_one(
        {"id": test_id},
        {"$set": {
            "status": "in_progress",
            "started_at": now.isoformat(),
            "ends_at": ends_at.isoformat(),
        }},
    )
    t.update({
        "status": "in_progress",
        "started_at": now.isoformat(),
        "ends_at": ends_at.isoformat(),
    })
    return t


# ---------------------------------------------------------------------------
# Autosave answers
# ---------------------------------------------------------------------------
@api_router.patch("/student/mock-tests/{test_id}/answers")
async def save_answers(
    test_id: str, payload: AnswersPatch, user: dict = Depends(get_current_user)
):
    _require_student(user)
    t = await db.mock_tests.find_one({"id": test_id}, {"_id": 0})
    if not t or t["student_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Mock test not found")
    if t["status"] not in ("in_progress",):
        raise HTTPException(
            status_code=409,
            detail="Mock test must be in progress to save answers",
        )
    # Refuse writes once timer expired.
    ends = _parse_iso(t.get("ends_at"))
    if ends and datetime.now(timezone.utc) > ends:
        await db.mock_tests.update_one(
            {"id": test_id}, {"$set": {"status": "expired"}}
        )
        raise HTTPException(status_code=409, detail="Time is up — submit to see your result")

    updates = {}
    for a in payload.answers:
        updates[f"answers.{a.question_id}"] = {
            "selected_option": a.selected_option,
            "text_answer": a.text_answer or "",
        }
    if updates:
        await db.mock_tests.update_one({"id": test_id}, {"$set": updates})
    return {"saved": len(updates)}


# ---------------------------------------------------------------------------
# Submit + auto-grade
# ---------------------------------------------------------------------------
def _grade_test(paper: dict, answers: dict) -> dict:
    """Score MCQs against correct_option; build topic-wise breakdown."""
    obtained = 0
    total = 0
    mcq_correct = 0
    mcq_total = 0
    by_topic: dict = {}

    for sec in paper.get("sections") or []:
        for q in sec.get("questions") or []:
            qid = q.get("id")
            marks = int(q.get("marks", 1) or 1)
            topic = q.get("topic", "Uncategorised")
            total += marks
            bt = by_topic.setdefault(topic, {"obtained": 0, "total": 0, "correct": 0, "count": 0})
            bt["total"] += marks
            bt["count"] += 1

            if (q.get("format") or "").lower() != "mcq":
                continue
            mcq_total += 1
            ans = (answers or {}).get(qid) or {}
            sel = ans.get("selected_option")
            correct = q.get("correct_option")
            if sel is not None and correct is not None and int(sel) == int(correct):
                obtained += marks
                mcq_correct += 1
                bt["obtained"] += marks
                bt["correct"] += 1

    return {
        "obtained": obtained,
        "total": total,
        "mcq_correct": mcq_correct,
        "mcq_total": mcq_total,
        "by_topic": by_topic,
        "percent": round((obtained / total) * 100, 1) if total else 0.0,
    }


@api_router.post("/student/mock-tests/{test_id}/submit")
async def submit_mock_test(test_id: str, user: dict = Depends(get_current_user)):
    _require_student(user)
    t = await db.mock_tests.find_one({"id": test_id}, {"_id": 0})
    if not t or t["student_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Mock test not found")
    if t["status"] == "submitted":
        return t
    if t["status"] == "not_started":
        raise HTTPException(status_code=409, detail="Start the test before submitting")

    paper = await db.papers.find_one({"id": t["paper_id"]}, {"_id": 0})
    if not paper:
        raise HTTPException(status_code=404, detail="Backing paper missing")

    score = _grade_test(paper, t.get("answers") or {})
    now = utcnow_iso()
    await db.mock_tests.update_one(
        {"id": test_id},
        {"$set": {"status": "submitted", "submitted_at": now, "score": score}},
    )
    t.update({"status": "submitted", "submitted_at": now, "score": score})
    t["paper"] = paper  # full paper with answers exposed
    logger.info(
        f"Mock test {test_id} submitted by {user['id']}: "
        f"{score['obtained']}/{score['total']} ({score['percent']}%)"
    )
    return t


@api_router.get("/student/mock-tests/{test_id}/result")
async def mock_test_result(test_id: str, user: dict = Depends(get_current_user)):
    _require_student(user)
    t = await db.mock_tests.find_one({"id": test_id}, {"_id": 0})
    if not t or t["student_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Mock test not found")
    if t["status"] not in ("submitted", "expired"):
        raise HTTPException(status_code=409, detail="Result available only after submission")
    paper = await db.papers.find_one({"id": t["paper_id"]}, {"_id": 0})
    # If the test expired without submit, grade now so the student still gets feedback.
    if t["status"] == "expired" and not t.get("score") and paper:
        score = _grade_test(paper, t.get("answers") or {})
        now = utcnow_iso()
        await db.mock_tests.update_one(
            {"id": test_id}, {"$set": {"score": score, "submitted_at": now}}
        )
        t["score"] = score
        t["submitted_at"] = now
    t["paper"] = paper
    return t
