"""FastAPI backend for AI Question Paper Generator."""
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

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
from llm_adapter import chat_complete, parse_json_response
from pdf_utils import chunk_text, extract_text, render_paper_pdf
from prompts import qgen_prompt, topic_extract_prompt
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
    textbook_id: str
    topics: List[str]  # selected topic names
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
    if len(data) > 30 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 30MB)")

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
@api_router.post("/papers/generate")
async def generate_paper(req: PaperRequest, user: dict = Depends(get_current_user)):
    dist = req.distribution or {}
    total = sum([dist.get(k, 0) for k in ("information", "concept", "application")])
    if total < 99 or total > 101:
        raise HTTPException(
            status_code=400, detail="Distribution must sum to 100%"
        )

    tb = await db.textbooks.find_one(
        {"id": req.textbook_id, "is_deleted": False}, {"_id": 0}
    )
    if not tb:
        raise HTTPException(status_code=404, detail="Textbook not found")
    if tb["owner_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")

    chunks = tb.get("chunks") or []
    context_excerpt = "\n\n".join(chunks[:6])[:10000]

    prompt = qgen_prompt(
        subject=req.subject,
        klass=req.class_name,
        topics=req.topics,
        difficulty=req.difficulty,
        distribution=dist,
        total_marks=req.total_marks,
        duration=req.duration_minutes,
        context_excerpt=context_excerpt,
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
        raise HTTPException(status_code=502, detail=f"Generation failed: {e}")

    # Attach ids to questions and flag important=False
    sections = data.get("sections") or []
    for s in sections:
        for q in s.get("questions", []):
            q["id"] = str(uuid.uuid4())
            q.setdefault("important", False)
            q.setdefault("marks", 2)
            q.setdefault("type", "concept")
            q.setdefault("difficulty", req.difficulty)

    paper_id = str(uuid.uuid4())
    paper_doc = {
        "id": paper_id,
        "owner_id": user["id"],
        "title": req.title,
        "subject": req.subject,
        "class_name": req.class_name,
        "textbook_id": req.textbook_id,
        "topics": req.topics,
        "difficulty": req.difficulty,
        "duration_minutes": req.duration_minutes,
        "total_marks": req.total_marks,
        "distribution": dist,
        "instructions": data.get("instructions", ""),
        "sections": sections,
        "created_at": utcnow_iso(),
        "is_deleted": False,
    }
    await db.papers.insert_one(paper_doc)
    paper_doc.pop("_id", None)
    return paper_doc


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
    # Support either Authorization header or ?auth= query param (for direct download links)
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
    pdf_bytes = render_paper_pdf(p)
    safe_title = "".join(c for c in p["title"] if c.isalnum() or c in (" ", "-", "_")).strip()[:60] or "paper"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.pdf"'
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
