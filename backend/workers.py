"""Background workers — long-running LLM jobs that run off the request loop
to bypass the 60s ingress proxy timeout.

These functions are imported and kicked off via `asyncio.create_task(...)` from
the API endpoints in `server.py`.
"""
from __future__ import annotations

import asyncio as _asyncio
import uuid
from typing import Optional

from fastapi import HTTPException

from deps import db, logger, utcnow_iso
from llm_adapter import chat_complete, generate_diagram, parse_json_response
from prompts import qgen_prompt, solution_prompt, SOLUTION_SYSTEM
from storage import APP_NAME, put_object


# ---------------------------------------------------------------------------
# Feedback hints — short summaries of past teacher edits, fed back into prompts
# ---------------------------------------------------------------------------
async def load_paper_feedback_hints(user_id: str, subject: str, class_name: str) -> str:
    """Build a short feedback-hints block from recent paper edits."""
    try:
        edits = (
            await db.paper_edits.find(
                {"owner_id": user_id, "subject": subject, "class_name": class_name},
                {"_id": 0},
            )
            .sort("created_at", -1)
            .to_list(8)
        )
    except Exception:
        return ""
    if not edits:
        return ""
    lines = []
    for e in edits:
        kind = e.get("edit_type")
        if kind == "modify_question":
            orig = (e.get("original") or "")[:150]
            new = (e.get("revised") or "")[:150]
            if orig and new:
                lines.append(f"- TEACHER REPHRASED: '{orig}'  →  '{new}'")
        elif kind == "delete_question":
            q = (e.get("original") or "")[:150]
            if q:
                lines.append(f"- TEACHER REMOVED style: '{q}' (avoid similar)")
        elif kind == "add_question":
            q = (e.get("revised") or "")[:150]
            if q:
                lines.append(f"- TEACHER ADDED style: '{q}' (prefer similar)")
    return "\n".join(lines[:10])


async def load_solution_feedback(user_id: str, subject: str, class_name: str) -> str:
    try:
        edits = (
            await db.solution_edits.find(
                {"owner_id": user_id, "subject": subject, "class_name": class_name},
                {"_id": 0},
            )
            .sort("created_at", -1)
            .to_list(8)
        )
    except Exception:
        return ""
    if not edits:
        return ""
    lines = []
    for e in edits:
        orig = (e.get("original") or "")[:180]
        new = (e.get("revised") or "")[:180]
        if orig and new:
            lines.append(f"- TEACHER REWORDED ANSWER: '{orig}'  →  '{new}'")
    return "\n".join(lines[:10])


# ---------------------------------------------------------------------------
# Diagram generation
# ---------------------------------------------------------------------------
async def generate_diagrams_for_paper(paper_id: str, owner_id: str, sections: list) -> list:
    """Generate diagrams (in parallel) for questions with needs_diagram=true.
    Saves PNGs to object storage and attaches `diagram_path` to each question.
    Best-effort: a failed diagram leaves the question without an image.
    """
    jobs = []
    targets = []
    for s in sections:
        for q in s.get("questions", []):
            if q.get("needs_diagram") and q.get("diagram_description"):
                targets.append(q)
                jobs.append(generate_diagram(q["diagram_description"]))
    if not jobs:
        return sections
    # Cap concurrency at 5 diagrams to avoid stalls
    jobs = jobs[:5]
    targets = targets[:5]
    results = await _asyncio.gather(*jobs, return_exceptions=True)
    for q, img_bytes in zip(targets, results):
        if isinstance(img_bytes, Exception) or not img_bytes:
            continue
        try:
            path = f"{APP_NAME}/diagrams/{owner_id}/{paper_id}/{q['id']}.png"
            saved = put_object(path, img_bytes, "image/png")
            q["diagram_path"] = saved["path"]
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Failed to save diagram: {e}")
    return sections


async def generate_diagrams_background(paper_id: str, owner_id: str) -> None:
    """Run diagram generation for a paper and update its sections in-place."""
    try:
        p = await db.papers.find_one(
            {"id": paper_id, "is_deleted": False}, {"_id": 0}
        )
        if not p:
            return
        sections = p.get("sections", [])
        sections = await generate_diagrams_for_paper(paper_id, owner_id, sections)
        # Mark statuses
        for s in sections:
            for q in s.get("questions", []):
                if q.get("diagram_path"):
                    q["diagram_status"] = "ready"
                elif q.get("diagram_status") == "pending":
                    q["diagram_status"] = "failed"
        await db.papers.update_one(
            {"id": paper_id},
            {"$set": {"sections": sections, "diagrams_pending": 0}},
        )
        logger.info(f"Diagram background job finished for {paper_id}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Diagram background job failed: {e}")


# ---------------------------------------------------------------------------
# Question paper generation
# ---------------------------------------------------------------------------
async def generate_paper_background(
    paper_id: str,
    owner_id: str,
    subject: str,
    klass: str,
    topics_weighted: list,
    difficulty: str,
    distribution: dict,
    total_marks: int,
    duration_minutes: int,
    context_excerpt: str,
    feedback_hints: str,
    format_distribution: Optional[dict] = None,
    custom_instructions: str = "",
    section_blueprint: str = "",
) -> None:
    """Run question generation off the request loop so the LLM call doesn't
    burst the 60s ingress timeout. Writes the result back to the paper doc
    and updates `generation_status`."""
    prompt = qgen_prompt(
        subject=subject,
        klass=klass,
        topics_weighted=topics_weighted,
        difficulty=difficulty,
        distribution=distribution,
        total_marks=total_marks,
        duration=duration_minutes,
        context_excerpt=context_excerpt,
        feedback_hints=feedback_hints,
        format_distribution=format_distribution or {},
        custom_instructions=custom_instructions or "",
        section_blueprint=section_blueprint or "",
    )
    try:
        raw = await chat_complete(
            system_message=(
                "You create original, high-quality exam questions in strict JSON. "
                "Never copy textbook content."
            ),
            user_text=prompt,
        )
        data = parse_json_response(raw)
    except Exception as e:  # noqa: BLE001
        logger.exception("Question generation failed")
        await db.papers.update_one(
            {"id": paper_id},
            {"$set": {
                "generation_status": "failed",
                "generation_error": str(e)[:500],
            }},
        )
        return

    sections = data.get("sections") or []
    for s in sections:
        for q in s.get("questions", []):
            q["id"] = str(uuid.uuid4())
            q.setdefault("important", False)
            q.setdefault("marks", 2)
            q.setdefault("type", "concept")
            q.setdefault("difficulty", difficulty)
            q.setdefault("needs_diagram", False)
            q.setdefault("format", "")
            # MCQ structured fields — keep options as a 4-string list and
            # correct_option as a 0-3 int. Drop them for non-MCQ items.
            if (q.get("format") or "").lower() == "mcq":
                opts = q.get("options") or []
                if isinstance(opts, list):
                    opts = [str(o).strip() for o in opts][:4]
                else:
                    opts = []
                q["options"] = opts
                try:
                    co = int(q.get("correct_option", 0))
                except (TypeError, ValueError):
                    co = 0
                q["correct_option"] = co if 0 <= co < len(opts) else 0
            else:
                q.pop("options", None)
                q.pop("correct_option", None)

    # Mark diagram jobs pending so the UI can show "generating" placeholders.
    pending_count = 0
    for s in sections:
        for q in s.get("questions", []):
            if q.get("needs_diagram") and q.get("diagram_description"):
                q["diagram_status"] = "pending"
                pending_count += 1
            else:
                q["diagram_status"] = "none"

    await db.papers.update_one(
        {"id": paper_id},
        {"$set": {
            "instructions": data.get("instructions", ""),
            "sections": sections,
            "diagrams_pending": pending_count,
            "generation_status": "ready",
            "generation_error": None,
            "recovered_from_truncation": bool(data.get("_recovered_from_truncation")),
        }},
    )

    # Kick off diagram generation asynchronously.
    if pending_count > 0:
        await generate_diagrams_background(paper_id, owner_id)


# ---------------------------------------------------------------------------
# Solution generation (synchronous build + async batched background)
# ---------------------------------------------------------------------------
async def build_solution_for_paper(paper: dict, user_id: str) -> dict:
    """Generate a solution for a single paper. Returns the solution dict.
    Raises HTTPException on failure. Does not persist.
    Questions are processed in batches of 5 so long/hard papers don't blow
    past LLM token limits or trigger gateway timeouts."""
    BATCH_SIZE = 5

    questions_payload = []
    for s in paper.get("sections", []):
        for q in s.get("questions", []):
            if not q.get("question"):
                continue
            questions_payload.append({
                "id": q["id"],
                "question": q["question"],
                "type": q.get("type", "concept"),
                "marks": q.get("marks", 2),
            })
    if not questions_payload:
        raise HTTPException(status_code=400, detail="Paper has no questions to solve")

    tb_ids = paper.get("textbook_ids") or (
        [paper["textbook_id"]] if paper.get("textbook_id") else []
    )
    merged_chunks: list = []
    max_per = max(2, 5 // max(1, len(tb_ids)))
    for tid in tb_ids:
        tb = await db.textbooks.find_one(
            {"id": tid, "is_deleted": False}, {"_id": 0}
        )
        if tb:
            merged_chunks.extend((tb.get("chunks") or [])[:max_per])
    context_excerpt = "\n\n".join(merged_chunks)[:8000]

    feedback_hints = await load_solution_feedback(
        user_id, paper.get("subject", ""), paper.get("class_name", "")
    )

    answers: dict[str, str] = {}
    last_err: Exception | None = None
    n_batches = (len(questions_payload) + BATCH_SIZE - 1) // BATCH_SIZE
    for bi in range(n_batches):
        batch = questions_payload[bi * BATCH_SIZE : (bi + 1) * BATCH_SIZE]
        prompt = solution_prompt(
            subject=paper.get("subject", ""),
            klass=paper.get("class_name", ""),
            context_excerpt=context_excerpt,
            questions_payload=batch,
            feedback_hints=feedback_hints,
        )
        for attempt in range(2):
            try:
                raw = await chat_complete(
                    system_message=SOLUTION_SYSTEM, user_text=prompt
                )
                data = parse_json_response(raw)
                for a in data.get("answers") or []:
                    qid = a.get("question_id")
                    text = (a.get("answer") or "").strip()
                    if qid and text:
                        answers[qid] = text
                last_err = None
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning(
                    f"Solution batch {bi + 1}/{n_batches} attempt {attempt + 1} failed: {e}"
                )

    if not answers and last_err:
        raise HTTPException(
            status_code=502, detail=f"Solution failed: {last_err}"
        )

    solution_sections = []
    for s in paper.get("sections", []):
        ans_list = []
        for q in s.get("questions", []):
            ans_list.append(
                {"question_id": q["id"], "answer": answers.get(q["id"], "")}
            )
        solution_sections.append(
            {"title": s.get("title", "Section"), "answers": ans_list}
        )
    return {
        "generated_at": utcnow_iso(),
        "is_stale": False,
        "sections": solution_sections,
    }


async def generate_solution_background(paper_id: str, user_id: str) -> None:
    """Run batched solution generation, updating the paper doc as each batch
    completes so the frontend can show progress."""
    BATCH_SIZE = 5
    try:
        p = await db.papers.find_one(
            {"id": paper_id, "is_deleted": False}, {"_id": 0}
        )
        if not p:
            return

        questions_payload: list = []
        for s in p.get("sections", []):
            for q in s.get("questions", []):
                if not q.get("question"):
                    continue
                questions_payload.append({
                    "id": q["id"],
                    "question": q["question"],
                    "type": q.get("type", "concept"),
                    "marks": q.get("marks", 2),
                })

        tb_ids = p.get("textbook_ids") or (
            [p["textbook_id"]] if p.get("textbook_id") else []
        )
        merged_chunks: list = []
        max_per = max(2, 5 // max(1, len(tb_ids)))
        for tid in tb_ids:
            tb = await db.textbooks.find_one(
                {"id": tid, "is_deleted": False}, {"_id": 0}
            )
            if tb:
                merged_chunks.extend((tb.get("chunks") or [])[:max_per])
        context_excerpt = "\n\n".join(merged_chunks)[:8000]

        feedback_hints = await load_solution_feedback(
            user_id, p.get("subject", ""), p.get("class_name", "")
        )

        answers: dict[str, str] = {}
        n_batches = (len(questions_payload) + BATCH_SIZE - 1) // BATCH_SIZE
        for bi in range(n_batches):
            batch = questions_payload[bi * BATCH_SIZE : (bi + 1) * BATCH_SIZE]
            prompt = solution_prompt(
                subject=p.get("subject", ""),
                klass=p.get("class_name", ""),
                context_excerpt=context_excerpt,
                questions_payload=batch,
                feedback_hints=feedback_hints,
            )
            for attempt in range(2):
                try:
                    raw = await chat_complete(
                        system_message=SOLUTION_SYSTEM, user_text=prompt
                    )
                    data = parse_json_response(raw)
                    for a in data.get("answers") or []:
                        qid = a.get("question_id")
                        text = (a.get("answer") or "").strip()
                        if qid and text:
                            answers[qid] = text
                    break
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        f"Solution batch {bi + 1}/{n_batches} attempt {attempt + 1} failed: {e}"
                    )

            # After each batch, persist progress so the UI can show it
            current = await db.papers.find_one(
                {"id": paper_id}, {"_id": 0, "solution": 1}
            )
            sol = (current or {}).get("solution") or {}
            for sec in sol.get("sections", []):
                for ans in sec.get("answers", []):
                    qid = ans.get("question_id")
                    if qid in answers:
                        ans["answer"] = answers[qid]
            sol["completed"] = sum(
                1
                for sec in sol.get("sections", [])
                for ans in sec.get("answers", [])
                if ans.get("answer")
            )
            sol["status"] = "generating"
            await db.papers.update_one(
                {"id": paper_id}, {"$set": {"solution": sol}}
            )

        # Mark complete (or partial)
        current = await db.papers.find_one(
            {"id": paper_id}, {"_id": 0, "solution": 1}
        )
        sol = (current or {}).get("solution") or {}
        completed = sol.get("completed", 0)
        sol["status"] = "ready" if completed == sol.get("total", 0) else "partial"
        sol["finished_at"] = utcnow_iso()
        await db.papers.update_one(
            {"id": paper_id}, {"$set": {"solution": sol}}
        )
        logger.info(
            f"Solution background job finished for {paper_id}: {completed}/{sol.get('total', 0)}"
        )
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Solution background job crashed: {e}")
        await db.papers.update_one(
            {"id": paper_id},
            {"$set": {"solution.status": "failed", "solution.error": str(e)[:300]}},
        )
