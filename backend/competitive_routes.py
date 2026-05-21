"""Competitive-exam endpoints + RAG-calibrated paper generation.

Conceptual model:
    competitive_exams (e.g. "JEE Main", "NEET", "CAT")
    └─ past_papers (PDFs uploaded by teachers; ingested in the background)
        └─ past_questions (extracted, tagged with topic+difficulty,
                           embedded for similarity search)

When a teacher generates a fresh practice paper for an exam, we retrieve
similar past questions (per topic) and pass them to the LLM as anchors so
the model calibrates difficulty against what *that specific exam* really
looks like, rather than relying on its priors.
"""
from __future__ import annotations

import asyncio as _asyncio
import uuid
from typing import Optional

from fastapi import Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth import get_current_user
from deps import api_router, db, logger, utcnow_iso
from exam_formats import EXAM_FORMATS, get_format
from llm_adapter import chain_for_exam, chat_complete, parse_json_response
from pdf_utils import chunk_text, extract_text
from prompts import (
    QPAPER_EXTRACT_SYSTEM,
    qpaper_extract_prompt,
    competitive_qgen_prompt,
    competitive_system_for_exam,
)
from rag import top_k_similar, difficulty_distribution
from storage import APP_NAME, put_object


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class ExamCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    description: str = ""
    is_shared: bool = True
    exam_type: str = "GENERIC"  # JEE_MAINS | JEE_ADV | CAT | UPSC | NEET | GENERIC


class CompetitivePaperRequest(BaseModel):
    exam_id: str
    title: str = "Practice Paper"
    topics: list[str] = Field(..., min_length=1)
    difficulty: str = "medium"
    question_count: int = Field(10, ge=3, le=200)
    duration_minutes: int = Field(60, ge=5, le=300)
    format_distribution: dict = Field(default_factory=lambda: {"mcq": 100})
    custom_instructions: str = ""


@api_router.get("/competitive-exams/formats")
async def competitive_exam_formats(user: dict = Depends(get_current_user)):
    """Locked-format catalogue. UI uses this to render the canonical
    question-count/duration/marks for each preset exam and to hide editable
    inputs for those. Auth-required (no PII, but no need to leak internals)."""
    return EXAM_FORMATS


# ---------------------------------------------------------------------------
# Exam CRUD
# ---------------------------------------------------------------------------
@api_router.post("/competitive-exams")
async def create_exam(payload: ExamCreate, user: dict = Depends(get_current_user)):
    if user["role"] not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Teacher or admin only")
    exam_id = str(uuid.uuid4())
    doc = {
        "id": exam_id,
        "name": payload.name.strip(),
        "description": payload.description.strip(),
        "is_shared": bool(payload.is_shared),
        "exam_type": (payload.exam_type or "GENERIC").upper(),
        "owner_id": user["id"],
        "papers_count": 0,
        "questions_count": 0,
        "created_at": utcnow_iso(),
        "is_deleted": False,
    }
    await db.competitive_exams.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/competitive-exams")
async def list_exams(user: dict = Depends(get_current_user)):
    if user["role"] == "student":
        q = {"is_deleted": False, "is_shared": True}
    elif user["role"] == "admin":
        q = {"is_deleted": False}
    else:
        q = {"is_deleted": False, "$or": [{"owner_id": user["id"]}, {"is_shared": True}]}
    rows = await db.competitive_exams.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    for r in rows:
        r.setdefault("exam_type", "GENERIC")
    return rows


@api_router.get("/competitive-exams/{exam_id}")
async def get_exam(exam_id: str, user: dict = Depends(get_current_user)):
    exam = await db.competitive_exams.find_one(
        {"id": exam_id, "is_deleted": False}, {"_id": 0}
    )
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    exam.setdefault("exam_type", "GENERIC")
    if (
        not exam.get("is_shared")
        and exam.get("owner_id") != user["id"]
        and user["role"] != "admin"
    ):
        raise HTTPException(status_code=403, detail="Forbidden")
    # Topic histogram across indexed past questions.
    topic_counts: dict = {}
    diff_counts = {"easy": 0, "medium": 0, "hard": 0}
    async for q in db.past_questions.find(
        {"exam_id": exam_id}, {"_id": 0, "topic": 1, "difficulty": 1}
    ):
        t = (q.get("topic") or "Uncategorised").strip()
        topic_counts[t] = topic_counts.get(t, 0) + 1
        d = (q.get("difficulty") or "").lower()
        if d in diff_counts:
            diff_counts[d] += 1
    exam["topic_counts"] = topic_counts
    exam["difficulty_counts"] = diff_counts
    papers = (
        await db.past_papers.find(
            {"exam_id": exam_id, "is_deleted": False}, {"_id": 0}
        )
        .sort("created_at", -1)
        .to_list(200)
    )
    exam["papers"] = papers
    return exam


# ---------------------------------------------------------------------------
# Upload past paper -> ingest -> embed
# ---------------------------------------------------------------------------
async def _ingest_past_paper(paper_id: str, exam_id: str, pdf_bytes: bytes) -> None:
    """Background ingestion: extract text, LLM-parse questions, persist."""
    try:
        text = extract_text(pdf_bytes)
        # Cap so we don't blow past prompt limits — for big papers process
        # in chunks of ~6000 chars each.
        chunks = chunk_text(text, chunk_size=6000, overlap=200)[:6]
        all_questions: list = []
        for ch in chunks:
            try:
                raw = await chat_complete(
                    system_message=QPAPER_EXTRACT_SYSTEM,
                    user_text=qpaper_extract_prompt(ch),
                )
                data = parse_json_response(raw)
                for q in data.get("questions") or []:
                    qt = (q.get("question") or "").strip()
                    if not qt or len(qt) < 8:
                        continue
                    all_questions.append({
                        "id": str(uuid.uuid4()),
                        "exam_id": exam_id,
                        "paper_id": paper_id,
                        "text": qt,
                        "marks": int(q.get("marks", 2) or 2),
                        "type": q.get("type", "concept"),
                        "difficulty": (q.get("difficulty") or "medium").lower(),
                        "topic": (q.get("topic") or "").strip(),
                        "created_at": utcnow_iso(),
                    })
            except Exception as e:  # noqa: BLE001
                logger.warning(f"past-paper chunk parse failed: {e}")
                continue

        if all_questions:
            await db.past_questions.insert_many(all_questions)
        await db.past_papers.update_one(
            {"id": paper_id},
            {"$set": {
                "status": "ready" if all_questions else "extraction_empty",
                "questions_count": len(all_questions),
            }},
        )
        await db.competitive_exams.update_one(
            {"id": exam_id},
            {"$inc": {"questions_count": len(all_questions)}},
        )
        logger.info(
            f"Ingested {len(all_questions)} questions into exam={exam_id} paper={paper_id}"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Past-paper ingestion failed")
        await db.past_papers.update_one(
            {"id": paper_id},
            {"$set": {"status": "failed", "error": str(e)[:300]}},
        )


@api_router.post("/competitive-exams/{exam_id}/papers/upload")
async def upload_past_paper(
    exam_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    if user["role"] not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Teacher or admin only")
    exam = await db.competitive_exams.find_one({"id": exam_id, "is_deleted": False})
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(pdf_bytes) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 100MB)")

    paper_id = str(uuid.uuid4())
    path = f"{APP_NAME}/competitive/{exam_id}/{paper_id}.pdf"
    try:
        put_object(path, pdf_bytes, "application/pdf")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"storage failed (non-fatal): {e}")

    doc = {
        "id": paper_id,
        "exam_id": exam_id,
        "original_filename": file.filename,
        "uploaded_by": user["id"],
        "storage_path": path,
        "status": "ingesting",
        "questions_count": 0,
        "error": None,
        "created_at": utcnow_iso(),
        "is_deleted": False,
    }
    await db.past_papers.insert_one(doc)
    await db.competitive_exams.update_one(
        {"id": exam_id}, {"$inc": {"papers_count": 1}}
    )

    _asyncio.create_task(_ingest_past_paper(paper_id, exam_id, pdf_bytes))
    doc.pop("_id", None)
    return doc


@api_router.delete("/competitive-exams/{exam_id}/papers/{paper_id}")
async def delete_past_paper(
    exam_id: str, paper_id: str, user: dict = Depends(get_current_user)
):
    if user["role"] not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Teacher or admin only")
    p = await db.past_papers.find_one({"id": paper_id, "exam_id": exam_id})
    if not p:
        raise HTTPException(status_code=404, detail="Past paper not found")
    if p["uploaded_by"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.past_papers.update_one({"id": paper_id}, {"$set": {"is_deleted": True}})
    # Tombstone the questions too so RAG retrieval ignores them.
    res = await db.past_questions.delete_many({"paper_id": paper_id})
    await db.competitive_exams.update_one(
        {"id": exam_id},
        {"$inc": {"papers_count": -1, "questions_count": -res.deleted_count}},
    )
    return {"deleted_questions": res.deleted_count}


# ---------------------------------------------------------------------------
# RAG-calibrated paper generation
# ---------------------------------------------------------------------------
async def _retrieve_anchors(exam_id: str, topics: list[str], k_per_topic: int = 3) -> list[dict]:
    """For each topic build a focused similarity query and grab top-K
    anchors. Deduplicate by question_id."""
    corpus = await db.past_questions.find(
        {"exam_id": exam_id},
        {"_id": 0, "id": 1, "text": 1, "topic": 1, "difficulty": 1, "marks": 1, "type": 1},
    ).to_list(5000)
    if not corpus:
        return []
    seen: set = set()
    anchors: list = []
    for t in topics:
        # Use topic name itself as the query; works well for short topic anchors.
        hits = top_k_similar(t, corpus, k=k_per_topic)
        for h in hits:
            if h["id"] in seen:
                continue
            seen.add(h["id"])
            anchors.append(h)
    return anchors


def _normalise_questions(
    sections: list,
    default_difficulty: str,
    strict_mcq: bool = False,
) -> list:
    """In-place normalise sections + return the flat question list.

    When `strict_mcq` is True (used for JEE_MAINS / JEE_ADV / CAT / UPSC /
    NEET — all locked to 100% 4-option MCQ), any question that arrives
    without exactly 4 options or with no valid correct_option is DROPPED
    rather than degraded. Batching gives us extra questions to absorb the
    occasional reject."""
    for s in sections:
        kept: list = []
        for q in s.get("questions", []):
            q["id"] = str(uuid.uuid4())
            q.setdefault("important", False)
            q.setdefault("marks", 1)
            q.setdefault("type", "concept")
            q.setdefault("difficulty", default_difficulty)
            q.setdefault("needs_diagram", False)
            q.setdefault("format", "")

            opts = q.get("options") or []
            if isinstance(opts, list):
                opts = [str(o).strip() for o in opts if str(o).strip()][:4]
            else:
                opts = []

            if strict_mcq:
                # In MCQ-only mode every question MUST be a valid 4-option MCQ.
                if len(opts) != 4:
                    continue  # drop
                try:
                    co = int(q.get("correct_option", 0))
                except (TypeError, ValueError):
                    co = 0
                if not (0 <= co <= 3):
                    continue  # drop
                q["format"] = "mcq"
                q["options"] = opts
                q["correct_option"] = co
                kept.append(q)
                continue

            # Lenient path (GENERIC exams): keep MCQ if options present,
            # otherwise treat as a free-form question.
            if (q.get("format") or "").lower() == "mcq":
                q["options"] = opts
                try:
                    co = int(q.get("correct_option", 0))
                except (TypeError, ValueError):
                    co = 0
                q["correct_option"] = co if 0 <= co < len(opts) else 0
            else:
                q.pop("options", None)
                q.pop("correct_option", None)
            kept.append(q)
        s["questions"] = kept
    return [q for s in sections for q in s.get("questions", [])]


async def _generate_one_batch(
    exam, exam_type: str, batch_topics: list[str], batch_count: int,
    batch_difficulty: str, batch_duration: int, anchors: list,
    rag_dist: dict, format_distribution: dict, custom_instructions: str,
    batch_index: int, batch_total: int,
) -> dict:
    """Single LLM call producing up to ~batch_count questions."""
    batch_instr = custom_instructions
    if batch_total > 1:
        batch_instr = (
            (custom_instructions + "\n\n" if custom_instructions else "")
            + f"This is batch {batch_index + 1} of {batch_total} for the full "
            f"paper. Generate EXACTLY {batch_count} ORIGINAL questions in this "
            "batch. Vary question style so subsequent batches don't repeat your phrasing."
        )
    prompt = competitive_qgen_prompt(
        exam_name=exam.get("name", "Competitive Exam"),
        topics=batch_topics,
        difficulty=batch_difficulty,
        question_count=batch_count,
        duration=batch_duration,
        anchors=anchors,
        rag_dist=rag_dist,
        format_distribution=format_distribution,
        custom_instructions=batch_instr,
        exam_type=exam_type,
    )
    raw = await chat_complete(
        system_message=competitive_system_for_exam(exam_type),
        user_text=prompt,
        provider_chain=chain_for_exam(exam_type),
    )
    return parse_json_response(raw)


async def _generate_competitive_paper(paper_id: str, req: CompetitivePaperRequest, user_id: str) -> None:
    """Background task that builds + writes a competitive paper using RAG.

    For preset exam_types (JEE_MAINS, NEET, …) the request's question_count,
    duration_minutes, total_marks and format_distribution are OVERRIDDEN
    with the official prescribed format from `exam_formats.EXAM_FORMATS`.

    Large papers (>batch_size questions) are generated in sequential
    batches and merged so we stay under the LLM output-token budget while
    still producing the full prescribed paper.
    """
    anchors: list = []
    rag_dist: dict = {"easy": 0, "medium": 0, "hard": 0}
    exam_type = "GENERIC"
    recovered = False
    instructions = ""
    sections: list = []
    try:
        exam = await db.competitive_exams.find_one({"id": req.exam_id}, {"_id": 0})
        if not exam:
            raise RuntimeError(f"exam {req.exam_id} missing")
        exam_type = (exam.get("exam_type") or "GENERIC").upper()
        anchors = await _retrieve_anchors(req.exam_id, req.topics)
        rag_dist = difficulty_distribution(anchors)

        spec = get_format(exam_type)
        if spec:
            # Locked official format — override any client-side numbers.
            total_q = spec["question_count"]
            duration = spec["duration_minutes"]
            fmt_dist = dict(spec["format_distribution"])
            batch_size = spec["batch_size"]
        else:
            total_q = req.question_count
            duration = req.duration_minutes
            fmt_dist = req.format_distribution
            batch_size = max(req.question_count, 30)  # GENERIC: single batch

        # Compute batch plan (each batch ≤ batch_size).
        num_batches = max(1, (total_q + batch_size - 1) // batch_size)
        sizes = [total_q // num_batches] * num_batches
        for i in range(total_q - sum(sizes)):
            sizes[i] += 1

        all_questions: list = []
        for b_i, b_count in enumerate(sizes):
            try:
                data = await _generate_one_batch(
                    exam=exam,
                    exam_type=exam_type,
                    batch_topics=req.topics,
                    batch_count=b_count,
                    batch_difficulty=req.difficulty,
                    batch_duration=duration,
                    anchors=anchors,
                    rag_dist=rag_dist,
                    format_distribution=fmt_dist,
                    custom_instructions=req.custom_instructions,
                    batch_index=b_i,
                    batch_total=num_batches,
                )
            except Exception as be:  # noqa: BLE001
                logger.warning(f"Batch {b_i+1}/{num_batches} failed: {be}")
                continue
            if not instructions and data.get("instructions"):
                instructions = data["instructions"]
            if data.get("_recovered_from_truncation"):
                recovered = True
            for sec in data.get("sections") or []:
                all_questions.extend(sec.get("questions") or [])

        if not all_questions:
            raise RuntimeError("No questions produced across batches")

        # Truncate to the prescribed total in case batches over-produced.
        all_questions = all_questions[:total_q]

        # Group into 1 section labelled with the exam (we keep the section
        # blueprint simple; teachers can re-section in the editor if needed).
        sections = [{
            "title": (spec["label"] if spec else exam.get("name", "Practice Paper")),
            "questions": all_questions,
        }]
        # If the locked format is 100% MCQ, drop any rogue non-MCQ questions
        # so users never see broken (no-options) items.
        strict_mcq = (
            isinstance(fmt_dist, dict)
            and len(fmt_dist) == 1
            and (fmt_dist.get("mcq") or 0) >= 100
        )
        _normalise_questions(sections, req.difficulty, strict_mcq=strict_mcq)
    except Exception as e:  # noqa: BLE001
        logger.exception("Competitive paper generation failed")
        await db.papers.update_one(
            {"id": paper_id},
            {"$set": {
                "generation_status": "failed",
                "generation_error": str(e)[:500],
            }},
        )
        return

    spec = get_format(exam_type)
    await db.papers.update_one(
        {"id": paper_id},
        {"$set": {
            "instructions": instructions,
            "sections": sections,
            "diagrams_pending": 0,
            "generation_status": "ready",
            "generation_error": None,
            "rag_anchors_used": len(anchors),
            "rag_difficulty_distribution": rag_dist,
            "exam_type": exam_type,
            "recovered_from_truncation": recovered,
            "duration_minutes": spec["duration_minutes"] if spec else req.duration_minutes,
            "total_marks": spec["total_marks"] if spec else req.question_count,
            "format_distribution": (
                spec["format_distribution"] if spec else req.format_distribution
            ),
        }},
    )


@api_router.post("/competitive-exams/{exam_id}/generate-paper")
async def generate_competitive_paper(
    exam_id: str,
    req: CompetitivePaperRequest,
    user: dict = Depends(get_current_user),
):
    if user["role"] not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Teacher or admin only")
    if req.exam_id != exam_id:
        raise HTTPException(status_code=400, detail="exam_id mismatch in body")
    exam = await db.competitive_exams.find_one({"id": exam_id, "is_deleted": False})
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    paper_id = str(uuid.uuid4())
    # Lock to official format spec when exam_type is a known preset.
    spec = get_format((exam.get("exam_type") or "GENERIC").upper())
    if spec:
        locked_duration = spec["duration_minutes"]
        locked_total_marks = spec["total_marks"]
        locked_fmt = dict(spec["format_distribution"])
    else:
        locked_duration = req.duration_minutes
        locked_total_marks = req.question_count  # 1 mark per MCQ default
        locked_fmt = {
            k: int(v) for k, v in (req.format_distribution or {}).items() if int(v) > 0
        }
    paper_doc = {
        "id": paper_id,
        "owner_id": user["id"],
        "title": req.title,
        "subject": exam.get("name", "Competitive"),
        "class_name": "Competitive",
        "textbook_id": None,
        "textbook_ids": [],
        "topics": [{"name": t, "weight": 5} for t in req.topics],
        "difficulty": req.difficulty,
        "duration_minutes": locked_duration,
        "total_marks": locked_total_marks,
        "distribution": {"information": 30, "concept": 40, "application": 30},
        "format_distribution": locked_fmt,
        "custom_instructions": req.custom_instructions,
        "section_blueprint": "",
        "instructions": "",
        "sections": [],
        "diagrams_pending": 0,
        "generation_status": "pending",
        "generation_error": None,
        "is_competitive": True,
        "competitive_exam_id": exam_id,
        "created_at": utcnow_iso(),
        "is_deleted": False,
    }
    await db.papers.insert_one(paper_doc)

    _asyncio.create_task(_generate_competitive_paper(paper_id, req, user["id"]))
    paper_doc.pop("_id", None)
    return paper_doc


@api_router.get("/competitive-exams/{exam_id}/rag-preview")
async def rag_preview(
    exam_id: str,
    topic: str,
    k: int = 5,
    user: dict = Depends(get_current_user),
):
    """Preview what anchors RAG would retrieve for a topic. Used by the UI
    to show teachers what calibration the LLM will see."""
    if user["role"] not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Teacher or admin only")
    corpus = await db.past_questions.find(
        {"exam_id": exam_id},
        {"_id": 0, "id": 1, "text": 1, "topic": 1, "difficulty": 1, "marks": 1},
    ).to_list(5000)
    hits = top_k_similar(topic, corpus, k=k)
    return {"anchors": hits, "distribution": difficulty_distribution(hits)}
