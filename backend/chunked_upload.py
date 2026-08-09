"""Chunked textbook upload — sidesteps the ~25MB Cloudflare proxy body limit.

Flow:
  1. POST /api/textbooks/chunked/init  {filename, subject, class_name, is_shared, total_size}
     → returns { upload_id }
  2. POST /api/textbooks/chunked/part?upload_id=…&index=0
     with body = raw bytes of chunk (multipart or octet-stream)
     Repeat for each 8 MB chunk in order.
  3. POST /api/textbooks/chunked/complete  {upload_id, total_parts}
     → reassembles the parts, calls the existing put_object + async ingest,
       returns the textbook row (status: ingesting).

Parts land on disk under /tmp/qpgen_uploads/{upload_id}/{index}.bin. The
upload session is scoped to the calling user; expires after 30 min.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth import get_current_user
from deps import api_router, db, logger, utcnow_iso
from pdf_utils import chunk_text, extract_text
from storage import APP_NAME, put_object


UPLOAD_ROOT = Path("/tmp/qpgen_uploads")
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
MAX_TOTAL_SIZE = 300 * 1024 * 1024  # 300 MB hard cap


class ChunkedInitRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=200)
    subject: str = ""
    class_name: str = ""
    is_shared: bool = False
    total_size: int = Field(..., ge=1, le=MAX_TOTAL_SIZE)


class ChunkedCompleteRequest(BaseModel):
    upload_id: str
    total_parts: int = Field(..., ge=1, le=1000)


@api_router.post("/textbooks/chunked/init")
async def chunked_init(req: ChunkedInitRequest, user: dict = Depends(get_current_user)):
    if user["role"] not in ("teacher", "admin"):
        raise HTTPException(status_code=403, detail="Teacher or admin only")
    if not req.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")
    upload_id = str(uuid.uuid4())
    session_dir = UPLOAD_ROOT / upload_id
    session_dir.mkdir(exist_ok=True)
    await db.upload_sessions.insert_one({
        "upload_id": upload_id,
        "user_id": user["id"],
        "filename": req.filename,
        "subject": req.subject,
        "class_name": req.class_name,
        "is_shared": bool(req.is_shared) if user["role"] == "admin" else False,
        "total_size": req.total_size,
        "session_dir": str(session_dir),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"upload_id": upload_id}


@api_router.post("/textbooks/chunked/part")
async def chunked_part(
    upload_id: str = Form(...),
    index: int = Form(...),
    part: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    sess = await db.upload_sessions.find_one({"upload_id": upload_id})
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if index < 0 or index > 999:
        raise HTTPException(status_code=400, detail="Bad part index")
    data = await part.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty part")
    dest = Path(sess["session_dir"]) / f"{index:04d}.bin"
    dest.write_bytes(data)
    return {"index": index, "size": len(data)}


@api_router.post("/textbooks/chunked/complete")
async def chunked_complete(
    req: ChunkedCompleteRequest, user: dict = Depends(get_current_user)
):
    sess = await db.upload_sessions.find_one({"upload_id": req.upload_id})
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(status_code=404, detail="Upload session not found")
    session_dir = Path(sess["session_dir"])
    parts = sorted(session_dir.glob("*.bin"))
    if len(parts) != req.total_parts:
        raise HTTPException(
            status_code=400,
            detail=f"Missing parts: expected {req.total_parts}, got {len(parts)}",
        )

    # Reassemble on disk (streaming) so we don't spike memory on 60MB+ files.
    combined = session_dir / "combined.pdf"
    with combined.open("wb") as out:
        for p in parts:
            out.write(p.read_bytes())
    total_size = combined.stat().st_size
    if total_size != sess["total_size"]:
        logger.warning(
            f"upload {req.upload_id}: size mismatch declared={sess['total_size']} actual={total_size}"
        )

    pdf_bytes = combined.read_bytes()

    textbook_id = str(uuid.uuid4())
    storage_path = f"{APP_NAME}/textbooks/{user['id']}/{textbook_id}.pdf"
    try:
        put_object(storage_path, pdf_bytes, "application/pdf")
    except Exception as e:  # noqa: BLE001
        logger.error(f"storage upload failed for chunked textbook: {e}")
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {e}")

    doc = {
        "id": textbook_id,
        "owner_id": user["id"],
        "storage_path": storage_path,
        "original_filename": sess["filename"],
        "subject": sess["subject"],
        "class_name": sess["class_name"],
        "status": "ingesting",
        "chunk_count": 0,
        "chunks": [],
        "topics": [],
        "is_shared": bool(sess.get("is_shared") and user["role"] == "admin"),
        "created_at": utcnow_iso(),
        "is_deleted": False,
    }
    await db.textbooks.insert_one(doc)

    # Kick off OCR + chunking in a background task (matches the small-file
    # upload path); UI polls textbook.status to see indexed → ready.
    async def _ingest():
        try:
            text = await asyncio.to_thread(extract_text, pdf_bytes)
        except Exception as e:  # noqa: BLE001
            logger.error(f"chunked ingest extract failed for {textbook_id}: {e}")
            await db.textbooks.update_one(
                {"id": textbook_id},
                {"$set": {"status": "extraction_failed"}},
            )
            return
        chunks = chunk_text(text)
        await db.textbooks.update_one(
            {"id": textbook_id},
            {"$set": {
                "status": "indexed" if chunks else "extraction_failed",
                "chunk_count": len(chunks),
                "chunks": chunks[:120],
            }},
        )

    asyncio.create_task(_ingest())

    # Cleanup temp files (fire-and-forget).
    try:
        for p in session_dir.iterdir():
            try:
                p.unlink()
            except OSError:
                pass
        session_dir.rmdir()
    except OSError:
        pass
    await db.upload_sessions.delete_one({"upload_id": req.upload_id})

    return {
        "id": textbook_id,
        "status": "ingesting",
        "chunk_count": 0,
        "original_filename": sess["filename"],
        "is_shared": doc["is_shared"],
    }
