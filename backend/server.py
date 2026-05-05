"""FastAPI backend for AI Question Paper Generator."""
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

from auth import (
    create_token,
    decode_token,
    get_current_user,
    hash_password,
    require_role,
    verify_password,
)
from llm_adapter import chat_complete, generate_diagram, parse_json_response
from pdf_utils import chunk_text, extract_text, render_paper_pdf, render_solution_pdf
from prompts import (
    qgen_prompt,
    qpaper_extract_prompt,
    solution_prompt,
    topic_extract_prompt,
    QPAPER_EXTRACT_SYSTEM,
    SOLUTION_SYSTEM,
)
from storage import APP_NAME, get_object, init_storage, put_object

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="AI Question Paper Generator")
api_router = APIRouter(prefix="/api")


# =========================================================
# Models
# =========================================================
class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str
    role: str = "teacher"  # teacher or admin


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    email: EmailStr
    full_name: str
    role: str


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


class TextbookSummary(BaseModel):
    id: str
    original_filename: str
    subject: str
    class_name: str
    status: str
    topic_count: int = 0
    created_at: str


class Topic(BaseModel):
    name: str
    subtopics: List[str] = []


class PaperRequest(BaseModel):
    title: str
    subject: str
    class_name: str
    # Either textbook_id (legacy, single) OR textbook_ids (new, multiple).
    textbook_id: Optional[str] = None
    textbook_ids: Optional[List[str]] = None
    # topics: either a list of names (legacy) OR list of {name, weight}.
    topics: List[Any]
    difficulty: str = "medium"  # easy / medium / hard
    duration_minutes: int = 60
    total_marks: int = 50
    distribution: dict  # {information, concept, application}


class QuestionInput(BaseModel):
    question: str
    type: str = "concept"
    difficulty: str = "medium"
    marks: int = 2
    topic: Optional[str] = None


class QuestionUpdate(BaseModel):
    id: str
    question: Optional[str] = None
    type: Optional[str] = None
    difficulty: Optional[str] = None
    marks: Optional[int] = None
    important: Optional[bool] = None


class SectionUpdate(BaseModel):
    title: str
    questions: List[dict]  # full question dicts


class PaperUpdate(BaseModel):
    title: Optional[str] = None
    instructions: Optional[str] = None
    duration_minutes: Optional[int] = None
    total_marks: Optional[int] = None
    sections: Optional[List[SectionUpdate]] = None


class AnswerUpdate(BaseModel):
    question_id: str
    answer: str


class SolutionSectionUpdate(BaseModel):
    title: str
    answers: List[AnswerUpdate]


class SolutionPatch(BaseModel):
    sections: List[SolutionSectionUpdate]


# =========================================================
# Helpers
# =========================================================
def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def serialize_user(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "email": doc["email"],
        "full_name": doc["full_name"],
        "role": doc["role"],
    }


# =========================================================
# Startup
# =========================================================
@app.on_event("startup")
async def startup():
    try:
        init_storage()
    except Exception as e:  # noqa: BLE001
        logger.error(f"Storage init failed (will retry on first use): {e}")
    # indexes
    try:
        await db.users.create_index("email", unique=True)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"index create: {e}")


@app.on_event("shutdown")
async def shutdown():
    client.close()


# =========================================================
# Auth
# =========================================================
@api_router.post("/auth/register", response_model=AuthResponse)
async def register(data: RegisterInput):
    if data.role not in ("teacher", "admin"):
        raise HTTPException(status_code=400, detail="role must be teacher or admin")
    existing = await db.users.find_one({"email": data.email.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": data.email.lower(),
        "full_name": data.full_name,
        "role": data.role,
        "password_hash": hash_password(data.password),
        "created_at": utcnow_iso(),
    }
    await db.users.insert_one(doc)
    token = create_token(user_id, data.role, data.email.lower())
    return AuthResponse(token=token, user=UserPublic(**serialize_user(doc)))


@api_router.post("/auth/login", response_model=AuthResponse)
async def login(data: LoginInput):
    user = await db.users.find_one({"email": data.email.lower()}, {"_id": 0})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user["id"], user["role"], user["email"])
    return AuthResponse(token=token, user=UserPublic(**serialize_user(user)))


@api_router.get("/auth/me", response_model=UserPublic)
async def me(user: dict = Depends(get_current_user)):
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublic(**serialize_user(u))


# =========================================================
# Textbooks (PDF upload + topic extraction)
# =========================================================
@api_router.post("/textbooks/upload")
async def upload_textbook(
    file: UploadFile = File(...),
    subject: str = Query(...),
    class_name: str = Query(...),
    user: dict = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 500 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 500MB)")

    textbook_id = str(uuid.uuid4())
    path = f"{APP_NAME}/textbooks/{user['id']}/{textbook_id}.pdf"
    result = put_object(path, data, "application/pdf")

    # Extract text synchronously (POC)
    try:
        text = extract_text(data)
    except Exception as e:  # noqa: BLE001
        logger.error(f"PDF extraction failed: {e}")
        text = ""

    chunks = chunk_text(text)
    doc = {
        "id": textbook_id,
        "owner_id": user["id"],
        "storage_path": result["path"],
        "original_filename": file.filename,
        "subject": subject,
        "class_name": class_name,
        "status": "indexed" if chunks else "extraction_failed",
        "chunk_count": len(chunks),
        "chunks": chunks[:50],  # cap for POC
        "topics": [],
        "created_at": utcnow_iso(),
        "is_deleted": False,
    }
    await db.textbooks.insert_one(doc)

    return {
        "id": textbook_id,
        "status": doc["status"],
        "chunk_count": doc["chunk_count"],
        "original_filename": file.filename,
    }


@api_router.get("/textbooks")
async def list_textbooks(user: dict = Depends(get_current_user)):
    query = {"is_deleted": False}
    if user["role"] != "admin":
        query["owner_id"] = user["id"]
    items = (
        await db.textbooks.find(query, {"_id": 0, "chunks": 0}).sort("created_at", -1).to_list(200)
    )
    return [
        {
            "id": t["id"],
            "original_filename": t["original_filename"],
            "subject": t["subject"],
            "class_name": t["class_name"],
            "status": t["status"],
            "topic_count": len(t.get("topics", [])),
            "created_at": t["created_at"],
        }
        for t in items
    ]


@api_router.post("/textbooks/{textbook_id}/reindex")
async def reindex_textbook(textbook_id: str, user: dict = Depends(get_current_user)):
    """Re-parse the textbook's PDF from storage with the latest text cleaner.
    Useful when a textbook was indexed with heavy watermark noise and the
    boilerplate stripper has since been improved."""
    tb = await db.textbooks.find_one(
        {"id": textbook_id, "is_deleted": False}, {"_id": 0}
    )
    if not tb:
        raise HTTPException(status_code=404, detail="Textbook not found")
    if tb["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        data, _ct = get_object(tb["storage_path"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not fetch PDF: {e}")
    try:
        text = extract_text(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Re-extraction failed: {e}")
    chunks = chunk_text(text)
    await db.textbooks.update_one(
        {"id": textbook_id},
        {
            "$set": {
                "chunks": chunks[:50],
                "chunk_count": len(chunks),
                "status": "indexed" if chunks else "extraction_failed",
                "topics": [],  # force re-extraction
            }
        },
    )
    return {
        "id": textbook_id,
        "chunk_count": len(chunks),
        "status": "indexed" if chunks else "extraction_failed",
    }


@api_router.post("/textbooks/{textbook_id}/extract-topics")
async def extract_topics(textbook_id: str, user: dict = Depends(get_current_user)):
    tb = await db.textbooks.find_one({"id": textbook_id, "is_deleted": False}, {"_id": 0})
    if not tb:
        raise HTTPException(status_code=404, detail="Textbook not found")
    if tb["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    chunks = tb.get("chunks") or []
    if not chunks:
        raise HTTPException(status_code=400, detail="No indexed text available")

    # Use first 8 chunks as excerpt (fits into token budget)
    excerpt = "\n\n".join(chunks[:8])[:12000]
    prompt = topic_extract_prompt(tb["subject"], tb["class_name"], excerpt)
    try:
        raw = await chat_complete(
            system_message=(
                "You analyse textbook content and output strict JSON only."
            ),
            user_text=prompt,
        )
        data = parse_json_response(raw)
        topics = data.get("topics", [])
        # normalize
        clean: list[dict] = []
        for t in topics:
            name = (t.get("name") or "").strip()
            if not name:
                continue
            subs = [s.strip() for s in (t.get("subtopics") or []) if s and s.strip()]
            clean.append({"name": name, "subtopics": subs[:8]})
        clean = clean[:12]
        await db.textbooks.update_one(
            {"id": textbook_id}, {"$set": {"topics": clean, "status": "topics_ready"}}
        )
        return {"topics": clean}
    except Exception as e:  # noqa: BLE001
        logger.exception("Topic extraction failed")
        raise HTTPException(status_code=502, detail=f"Topic extraction failed: {e}")


@api_router.get("/textbooks/{textbook_id}")
async def get_textbook(textbook_id: str, user: dict = Depends(get_current_user)):
    tb = await db.textbooks.find_one(
        {"id": textbook_id, "is_deleted": False},
        {"_id": 0, "chunks": 0},
    )
    if not tb:
        raise HTTPException(status_code=404, detail="Textbook not found")
    if tb["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return tb


@api_router.delete("/textbooks/{textbook_id}")
async def delete_textbook(textbook_id: str, user: dict = Depends(get_current_user)):
    tb = await db.textbooks.find_one({"id": textbook_id, "is_deleted": False}, {"_id": 0})
    if not tb:
        raise HTTPException(status_code=404, detail="Textbook not found")
    if tb["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    await db.textbooks.update_one({"id": textbook_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}


# =========================================================
# Papers
# =========================================================
async def _load_feedback_hints(user_id: str, subject: str, class_name: str) -> str:
    """Build a short feedback-hints block from recent user edits.

    We pull the most recent modify/add edits for the same subject+class and
    summarise them so the LLM can adapt future generations to teacher style."""
    try:
        edits = (
            await db.paper_edits.find(
                {
                    "owner_id": user_id,
                    "subject": subject,
                    "class_name": class_name,
                },
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


async def _generate_diagrams_for_paper(paper_id: str, owner_id: str, sections: list) -> list:
    """Generate diagrams (in parallel) for questions with needs_diagram=true.

    Saves PNGs to object storage and attaches `diagram_path` to each question.
    Best-effort: a failed diagram leaves the question without an image.
    """
    import asyncio as _asyncio

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


@api_router.post("/papers/generate")
async def generate_paper(req: PaperRequest, user: dict = Depends(get_current_user)):
    dist = req.distribution or {}
    total = sum([dist.get(k, 0) for k in ("information", "concept", "application")])
    if total < 99 or total > 101:
        raise HTTPException(
            status_code=400, detail="Distribution must sum to 100%"
        )

    # Resolve textbook list (support both legacy single + new multi)
    tb_ids: list = []
    if req.textbook_ids:
        tb_ids.extend(req.textbook_ids)
    if req.textbook_id and req.textbook_id not in tb_ids:
        tb_ids.append(req.textbook_id)
    tb_ids = [x for x in tb_ids if x]
    if not tb_ids:
        raise HTTPException(status_code=400, detail="At least one textbook required")

    textbooks: list = []
    for tid in tb_ids:
        tb = await db.textbooks.find_one(
            {"id": tid, "is_deleted": False}, {"_id": 0}
        )
        if not tb:
            raise HTTPException(status_code=404, detail=f"Textbook {tid} not found")
        if tb["owner_id"] != user["id"] and user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Forbidden")
        textbooks.append(tb)

    # Interleave chunks from each textbook so context spans the full book list
    merged_chunks: list = []
    max_per = max(2, 8 // max(1, len(textbooks)))
    for tb in textbooks:
        merged_chunks.extend((tb.get("chunks") or [])[:max_per])
    context_excerpt = "\n\n".join(merged_chunks)[:10000]

    feedback_hints = await _load_feedback_hints(
        user["id"], req.subject, req.class_name
    )

    # Normalise topics to weighted form: [{"name": str, "weight": int}, ...]
    topics_weighted: list = []
    for t in req.topics or []:
        if isinstance(t, str):
            topics_weighted.append({"name": t.strip(), "weight": 5})
        elif isinstance(t, dict) and t.get("name"):
            topics_weighted.append(
                {
                    "name": str(t["name"]).strip(),
                    "weight": max(1, int(t.get("weight", 5))),
                }
            )
    topics_weighted = [t for t in topics_weighted if t["name"]]
    if not topics_weighted:
        raise HTTPException(status_code=400, detail="At least one topic required")

    # Insert a placeholder paper immediately so we can return its id within
    # the proxy's 60s budget. The actual LLM call runs in a background task.
    paper_id = str(uuid.uuid4())
    paper_doc = {
        "id": paper_id,
        "owner_id": user["id"],
        "title": req.title,
        "subject": req.subject,
        "class_name": req.class_name,
        "textbook_id": tb_ids[0],  # legacy single for back-compat
        "textbook_ids": tb_ids,
        "topics": topics_weighted,
        "difficulty": req.difficulty,
        "duration_minutes": req.duration_minutes,
        "total_marks": req.total_marks,
        "distribution": dist,
        "instructions": "",
        "sections": [],
        "diagrams_pending": 0,
        "generation_status": "pending",
        "generation_error": None,
        "created_at": utcnow_iso(),
        "is_deleted": False,
    }
    await db.papers.insert_one(paper_doc)
    paper_doc.pop("_id", None)

    import asyncio as _asyncio

    _asyncio.create_task(
        _generate_paper_background(
            paper_id=paper_id,
            owner_id=user["id"],
            subject=req.subject,
            klass=req.class_name,
            topics_weighted=topics_weighted,
            difficulty=req.difficulty,
            distribution=dist,
            total_marks=req.total_marks,
            duration_minutes=req.duration_minutes,
            context_excerpt=context_excerpt,
            feedback_hints=feedback_hints,
        )
    )

    return paper_doc


async def _generate_paper_background(
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
        }},
    )

    # Kick off diagram generation asynchronously.
    if pending_count > 0:
        await _generate_diagrams_background(paper_id, owner_id)


async def _generate_diagrams_background(paper_id: str, owner_id: str) -> None:
    """Run diagram generation for a paper and update its sections in-place."""
    try:
        p = await db.papers.find_one(
            {"id": paper_id, "is_deleted": False}, {"_id": 0}
        )
        if not p:
            return
        sections = p.get("sections", [])
        sections = await _generate_diagrams_for_paper(paper_id, owner_id, sections)
        # Mark statuses
        remaining = 0
        for s in sections:
            for q in s.get("questions", []):
                if q.get("diagram_path"):
                    q["diagram_status"] = "ready"
                elif q.get("diagram_status") == "pending":
                    q["diagram_status"] = "failed"
                    remaining += 1
        await db.papers.update_one(
            {"id": paper_id},
            {"$set": {"sections": sections, "diagrams_pending": 0}},
        )
        logger.info(f"Diagram background job finished for {paper_id}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Diagram background job failed: {e}")


@api_router.patch("/papers/{paper_id}")
async def update_paper(
    paper_id: str,
    update: PaperUpdate,
    user: dict = Depends(get_current_user),
):
    """Edit paper content (title, meta, questions). Logs each question-level
    change into `paper_edits` for the AI feedback loop."""
    p = await db.papers.find_one(
        {"id": paper_id, "is_deleted": False}, {"_id": 0}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if p["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    set_fields: dict = {}
    if update.title is not None:
        set_fields["title"] = update.title
    if update.instructions is not None:
        set_fields["instructions"] = update.instructions
    if update.duration_minutes is not None:
        set_fields["duration_minutes"] = int(update.duration_minutes)
    if update.total_marks is not None:
        set_fields["total_marks"] = int(update.total_marks)

    if update.sections is not None:
        old_qs = {
            q["id"]: q for s in p.get("sections", []) for q in s.get("questions", [])
        }
        new_sections = []
        new_ids = set()
        for s in update.sections:
            clean_qs = []
            for q in s.questions:
                if not q.get("id"):
                    q["id"] = str(uuid.uuid4())
                q.setdefault("important", False)
                q.setdefault("marks", 2)
                q.setdefault("type", "concept")
                q.setdefault("difficulty", "medium")
                q.setdefault("needs_diagram", False)
                clean_qs.append(q)
                new_ids.add(q["id"])
                prev = old_qs.get(q["id"])
                if prev is None:
                    # Added
                    await db.paper_edits.insert_one({
                        "paper_id": paper_id,
                        "owner_id": user["id"],
                        "subject": p.get("subject", ""),
                        "class_name": p.get("class_name", ""),
                        "edit_type": "add_question",
                        "revised": q.get("question", ""),
                        "created_at": utcnow_iso(),
                    })
                elif prev.get("question") != q.get("question"):
                    await db.paper_edits.insert_one({
                        "paper_id": paper_id,
                        "owner_id": user["id"],
                        "subject": p.get("subject", ""),
                        "class_name": p.get("class_name", ""),
                        "edit_type": "modify_question",
                        "original": prev.get("question", ""),
                        "revised": q.get("question", ""),
                        "created_at": utcnow_iso(),
                    })
            new_sections.append({"title": s.title, "questions": clean_qs})

        # Detect deletions
        for qid, prev in old_qs.items():
            if qid not in new_ids:
                await db.paper_edits.insert_one({
                    "paper_id": paper_id,
                    "owner_id": user["id"],
                    "subject": p.get("subject", ""),
                    "class_name": p.get("class_name", ""),
                    "edit_type": "delete_question",
                    "original": prev.get("question", ""),
                    "created_at": utcnow_iso(),
                })
        set_fields["sections"] = new_sections

        # If a solution already exists, mark it stale so the UI prompts the
        # teacher to regenerate.
        if p.get("solution"):
            set_fields["solution.is_stale"] = True

    if set_fields:
        await db.papers.update_one({"id": paper_id}, {"$set": set_fields})
    updated = await db.papers.find_one({"id": paper_id}, {"_id": 0})
    return updated


@api_router.get("/papers")
async def list_papers(user: dict = Depends(get_current_user)):
    items = (
        await db.papers.find(
            {"owner_id": user["id"], "is_deleted": False},
            {"_id": 0, "sections": 0},
        )
        .sort("created_at", -1)
        .to_list(200)
    )
    return items


@api_router.get("/papers/{paper_id}")
async def get_paper(paper_id: str, user: dict = Depends(get_current_user)):
    p = await db.papers.find_one(
        {"id": paper_id, "is_deleted": False}, {"_id": 0}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if p["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    return p


@api_router.patch("/papers/{paper_id}/question/{question_id}/toggle-important")
async def toggle_important(
    paper_id: str, question_id: str, user: dict = Depends(get_current_user)
):
    p = await db.papers.find_one(
        {"id": paper_id, "owner_id": user["id"], "is_deleted": False}, {"_id": 0}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    changed = False
    for s in p.get("sections", []):
        for q in s.get("questions", []):
            if q.get("id") == question_id:
                q["important"] = not q.get("important", False)
                changed = True
                break
    if not changed:
        raise HTTPException(status_code=404, detail="Question not found")
    await db.papers.update_one(
        {"id": paper_id}, {"$set": {"sections": p["sections"]}}
    )
    return {"ok": True, "sections": p["sections"]}


@api_router.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str, user: dict = Depends(get_current_user)):
    p = await db.papers.find_one({"id": paper_id, "owner_id": user["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    await db.papers.update_one({"id": paper_id}, {"$set": {"is_deleted": True}})
    return {"ok": True}


@api_router.get("/papers/{paper_id}/pdf")
async def paper_pdf(
    paper_id: str,
    authorization: Optional[str] = Header(None),
    auth: Optional[str] = Query(None),
):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    payload = decode_token(token)
    user_id = payload["sub"]
    role = payload.get("role", "teacher")

    p = await db.papers.find_one(
        {"id": paper_id, "is_deleted": False}, {"_id": 0}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if p["owner_id"] != user_id and role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if p.get("generation_status") == "pending":
        raise HTTPException(status_code=409, detail="Paper is still being generated")
    if p.get("generation_status") == "failed":
        raise HTTPException(status_code=409, detail="Paper generation failed; nothing to download")

    def _diagram_loader(_qid: str, path: str):
        try:
            data, _ct = get_object(path)
            return data
        except Exception:
            return None

    pdf_bytes = render_paper_pdf(p, diagram_loader=_diagram_loader)
    safe_title = "".join(c for c in p["title"] if c.isalnum() or c in (" ", "-", "_")).strip()[:60] or "paper"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.pdf"'
        },
    )


@api_router.get("/papers/{paper_id}/diagrams/{question_id}")
async def paper_diagram(
    paper_id: str,
    question_id: str,
    authorization: Optional[str] = Header(None),
    auth: Optional[str] = Query(None),
):
    """Serve a question diagram PNG from object storage. Accepts either
    Authorization header or ?auth= query param (so <img src> works)."""
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    payload = decode_token(token)
    user_id = payload["sub"]
    role = payload.get("role", "teacher")

    p = await db.papers.find_one(
        {"id": paper_id, "is_deleted": False}, {"_id": 0}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if p["owner_id"] != user_id and role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    path = None
    for s in p.get("sections", []):
        for q in s.get("questions", []):
            if q.get("id") == question_id:
                path = q.get("diagram_path")
                break
    if not path:
        raise HTTPException(status_code=404, detail="Diagram not found")
    data, ct = get_object(path)
    return Response(content=data, media_type=ct or "image/png")


# =========================================================
# Solutions (answer keys)
# =========================================================
async def _load_solution_feedback(user_id: str, subject: str, class_name: str) -> str:
    try:
        edits = (
            await db.solution_edits.find(
                {
                    "owner_id": user_id,
                    "subject": subject,
                    "class_name": class_name,
                },
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
            lines.append(
                f"- TEACHER REWORDED ANSWER: '{orig}'  →  '{new}'"
            )
    return "\n".join(lines[:10])


async def _build_solution_for_paper(paper: dict, user_id: str) -> dict:
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

    feedback_hints = await _load_solution_feedback(
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
        for attempt in range(2):  # 1 retry on transient failure
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
        # Continue with next batch even if this one failed — partial solutions
        # are still useful; missing answers will simply be empty strings.

    if not answers and last_err:
        # All batches failed.
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


@api_router.post("/papers/{paper_id}/solution/generate")
async def generate_solution(paper_id: str, user: dict = Depends(get_current_user)):
    p = await db.papers.find_one(
        {"id": paper_id, "is_deleted": False}, {"_id": 0}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if p["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    # Build empty-shell solution immediately so the user gets a response in <1s.
    # Background task fills it in batch by batch and updates the paper doc.
    total = 0
    empty_sections = []
    for s in p.get("sections", []):
        ans_list = []
        for q in s.get("questions", []):
            if q.get("question"):
                ans_list.append({"question_id": q["id"], "answer": ""})
                total += 1
        empty_sections.append(
            {"title": s.get("title", "Section"), "answers": ans_list}
        )
    if total == 0:
        raise HTTPException(status_code=400, detail="Paper has no questions to solve")

    pending_solution = {
        "generated_at": utcnow_iso(),
        "is_stale": False,
        "status": "generating",
        "completed": 0,
        "total": total,
        "sections": empty_sections,
    }
    await db.papers.update_one(
        {"id": paper_id}, {"$set": {"solution": pending_solution}}
    )

    import asyncio as _asyncio

    _asyncio.create_task(
        _generate_solution_background(paper_id, user["id"])
    )
    return pending_solution


async def _generate_solution_background(paper_id: str, user_id: str) -> None:
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

        feedback_hints = await _load_solution_feedback(
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


@api_router.post("/papers/solutions/bulk-generate")
async def bulk_generate_solutions(
    only_missing: bool = Query(True, description="Skip papers that already have a solution"),
    only_stale: bool = Query(False, description="Only regenerate papers whose solution is stale"),
    user: dict = Depends(get_current_user),
):
    """Generate solutions for all of the user's existing papers in one pass.

    - `only_missing=true` (default): skip papers that already have a solution (unless stale=true too)
    - `only_stale=true`: only regenerate papers whose solution is marked stale
    If both flags are false, all papers get regenerated.
    """
    query = {"owner_id": user["id"], "is_deleted": False}
    papers = await db.papers.find(query, {"_id": 0}).to_list(200)

    queued: list = []
    for p in papers:
        has_sol = bool(p.get("solution"))
        is_stale = bool((p.get("solution") or {}).get("is_stale"))
        if only_stale:
            if not is_stale:
                continue
        elif only_missing:
            if has_sol and not is_stale:
                continue
        queued.append(p)

    succeeded: list = []
    failed: list = []
    for p in queued:
        try:
            solution = await _build_solution_for_paper(p, user["id"])
            await db.papers.update_one(
                {"id": p["id"]}, {"$set": {"solution": solution}}
            )
            succeeded.append({"id": p["id"], "title": p.get("title", "")})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Bulk solution failed for {p.get('id')}: {e}")
            failed.append({
                "id": p["id"],
                "title": p.get("title", ""),
                "error": str(e)[:200],
            })

    return {
        "processed": len(queued),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "succeeded_items": succeeded,
        "failed_items": failed,
    }


@api_router.patch("/papers/{paper_id}/solution")
async def update_solution(
    paper_id: str,
    update: SolutionPatch,
    user: dict = Depends(get_current_user),
):
    p = await db.papers.find_one(
        {"id": paper_id, "is_deleted": False}, {"_id": 0}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if p["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    current = p.get("solution") or {}
    if not current.get("sections"):
        raise HTTPException(
            status_code=400,
            detail="No solution exists yet. Generate it first.",
        )

    # Log edits (feedback loop)
    old_answers = {
        a.get("question_id"): (a.get("answer") or "")
        for sec in current.get("sections", [])
        for a in sec.get("answers", [])
    }
    new_sections = []
    for s in update.sections:
        new_answers = []
        for a in s.answers:
            old = old_answers.get(a.question_id, "")
            if old != a.answer:
                await db.solution_edits.insert_one({
                    "paper_id": paper_id,
                    "owner_id": user["id"],
                    "subject": p.get("subject", ""),
                    "class_name": p.get("class_name", ""),
                    "question_id": a.question_id,
                    "original": old,
                    "revised": a.answer,
                    "created_at": utcnow_iso(),
                })
            new_answers.append(
                {"question_id": a.question_id, "answer": a.answer}
            )
        new_sections.append({"title": s.title, "answers": new_answers})

    updated_solution = {
        "generated_at": current.get("generated_at"),
        "edited_at": utcnow_iso(),
        "is_stale": False,
        "sections": new_sections,
    }
    await db.papers.update_one(
        {"id": paper_id}, {"$set": {"solution": updated_solution}}
    )
    return updated_solution


@api_router.get("/papers/{paper_id}/solution/pdf")
async def solution_pdf(
    paper_id: str,
    authorization: Optional[str] = Header(None),
    auth: Optional[str] = Query(None),
):
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(status_code=401, detail="Missing token")
    payload = decode_token(token)
    user_id = payload["sub"]
    role = payload.get("role", "teacher")

    p = await db.papers.find_one(
        {"id": paper_id, "is_deleted": False}, {"_id": 0}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if p["owner_id"] != user_id and role != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if not p.get("solution"):
        raise HTTPException(status_code=400, detail="No solution generated yet")

    def _diagram_loader(_qid: str, path: str):
        try:
            data, _ct = get_object(path)
            return data
        except Exception:
            return None

    pdf_bytes = render_solution_pdf(p, diagram_loader=_diagram_loader)
    safe_title = (
        "".join(c for c in p["title"] if c.isalnum() or c in (" ", "-", "_"))
        .strip()[:60]
        or "paper"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title} - Solution.pdf"'
        },
    )


# =========================================================
# Question Bank (saving individual questions)
# =========================================================
@api_router.post("/qbank/save-from-paper/{paper_id}/{question_id}")
async def save_question(
    paper_id: str, question_id: str, user: dict = Depends(get_current_user)
):
    p = await db.papers.find_one(
        {"id": paper_id, "is_deleted": False}, {"_id": 0}
    )
    if not p:
        raise HTTPException(status_code=404, detail="Paper not found")
    if p["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    for s in p.get("sections", []):
        for q in s.get("questions", []):
            if q.get("id") == question_id:
                doc = {
                    "id": str(uuid.uuid4()),
                    "owner_id": user["id"],
                    "question": q.get("question"),
                    "type": q.get("type"),
                    "difficulty": q.get("difficulty"),
                    "marks": q.get("marks", 2),
                    "important": q.get("important", False),
                    "subject": p["subject"],
                    "class_name": p["class_name"],
                    "topics": p.get("topics", []),
                    "source_paper_id": paper_id,
                    "created_at": utcnow_iso(),
                    "is_deleted": False,
                }
                await db.qbank.insert_one(doc)
                doc.pop("_id", None)
                return doc
    raise HTTPException(status_code=404, detail="Question not found")


@api_router.post("/qbank")
async def create_qbank_question(
    data: QuestionInput, user: dict = Depends(get_current_user)
):
    doc = {
        "id": str(uuid.uuid4()),
        "owner_id": user["id"],
        "question": data.question,
        "type": data.type,
        "difficulty": data.difficulty,
        "marks": data.marks,
        "topic": data.topic,
        "important": False,
        "created_at": utcnow_iso(),
        "is_deleted": False,
    }
    await db.qbank.insert_one(doc)
    doc.pop("_id", None)
    return doc


@api_router.get("/qbank")
async def list_qbank(
    user: dict = Depends(get_current_user),
    q: Optional[str] = None,
    type_filter: Optional[str] = None,
    difficulty: Optional[str] = None,
):
    query: dict = {"owner_id": user["id"], "is_deleted": False}
    if type_filter:
        query["type"] = type_filter
    if difficulty:
        query["difficulty"] = difficulty
    if q:
        query["question"] = {"$regex": q, "$options": "i"}
    items = await db.qbank.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items


@api_router.delete("/qbank/{qid}")
async def delete_qbank(qid: str, user: dict = Depends(get_current_user)):
    await db.qbank.update_one(
        {"id": qid, "owner_id": user["id"]}, {"$set": {"is_deleted": True}}
    )
    return {"ok": True}


# =========================================================
# Upload existing question papers (teacher & admin)
# =========================================================
@api_router.post("/qpapers/upload")
async def upload_qpaper(
    file: UploadFile = File(...),
    subject: Optional[str] = Query(None),
    class_name: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
):
    """Upload an existing question-paper PDF. The system parses the PDF,
    extracts individual questions via the LLM and adds them to the user's
    question bank. Both teachers and admins can use this."""
    if user["role"] not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > 500 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 500MB)")

    # Save to object storage for audit/traceability
    qpaper_id = str(uuid.uuid4())
    path = f"{APP_NAME}/qpapers/{user['id']}/{qpaper_id}.pdf"
    try:
        put_object(path, data, "application/pdf")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Storage save failed (non-fatal): {e}")

    try:
        text = extract_text(data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")
    if not text.strip():
        raise HTTPException(status_code=400, detail="No text found in PDF")

    excerpt = text[:14000]
    try:
        raw = await chat_complete(
            system_message=QPAPER_EXTRACT_SYSTEM,
            user_text=qpaper_extract_prompt(excerpt),
        )
        parsed = parse_json_response(raw)
    except Exception as e:  # noqa: BLE001
        logger.exception("Question-paper extraction failed")
        raise HTTPException(status_code=502, detail=f"Extraction failed: {e}")

    questions = parsed.get("questions") or []
    subject = subject or parsed.get("subject") or ""
    class_name = class_name or parsed.get("class_name") or ""

    saved = 0
    saved_docs = []
    for q in questions:
        text_q = (q.get("question") or "").strip()
        if not text_q:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "owner_id": user["id"],
            "question": text_q,
            "type": q.get("type") or "concept",
            "difficulty": q.get("difficulty") or "medium",
            "marks": int(q.get("marks") or 2),
            "subject": subject,
            "class_name": class_name,
            "topics": [],
            "source": "uploaded",
            "source_file": file.filename,
            "important": False,
            "created_at": utcnow_iso(),
            "is_deleted": False,
        }
        await db.qbank.insert_one(doc)
        doc.pop("_id", None)
        saved_docs.append(doc)
        saved += 1

    return {
        "saved": saved,
        "subject": subject,
        "class_name": class_name,
        "filename": file.filename,
        "questions": saved_docs[:100],
    }


# =========================================================
# Health
# =========================================================
@api_router.get("/")
async def root():
    return {"message": "AI Question Paper Generator API"}


app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
