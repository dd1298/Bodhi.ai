"""Admin Dashboard endpoints. Imported once from server.py to register routes
on the shared `api_router`."""
from fastapi import Depends, HTTPException, Query

from auth import get_current_user
from deps import api_router, db, require_admin


@api_router.get("/admin/overview")
async def admin_overview(user: dict = Depends(get_current_user)):
    require_admin(user)
    teachers = await db.users.count_documents({"role": "teacher"})
    admins = await db.users.count_documents({"role": "admin"})
    textbooks_total = await db.textbooks.count_documents({"is_deleted": False})
    textbooks_shared = await db.textbooks.count_documents(
        {"is_deleted": False, "is_shared": True}
    )
    papers_total = await db.papers.count_documents({"is_deleted": False})
    papers_pending = await db.papers.count_documents(
        {"is_deleted": False, "generation_status": "pending"}
    )
    papers_failed = await db.papers.count_documents(
        {"is_deleted": False, "generation_status": "failed"}
    )
    return {
        "teachers": teachers,
        "admins": admins,
        "textbooks_total": textbooks_total,
        "textbooks_shared": textbooks_shared,
        "papers_total": papers_total,
        "papers_pending": papers_pending,
        "papers_failed": papers_failed,
    }


@api_router.get("/admin/users")
async def admin_users(user: dict = Depends(get_current_user)):
    require_admin(user)
    users = await db.users.find(
        {}, {"_id": 0, "password_hash": 0}
    ).sort("created_at", -1).to_list(500)
    out = []
    for u in users:
        tb_count = await db.textbooks.count_documents(
            {"is_deleted": False, "owner_id": u["id"]}
        )
        paper_count = await db.papers.count_documents(
            {"is_deleted": False, "owner_id": u["id"]}
        )
        out.append({**u, "textbook_count": tb_count, "paper_count": paper_count})
    return out


@api_router.get("/admin/textbooks")
async def admin_textbooks(user: dict = Depends(get_current_user)):
    require_admin(user)
    tbs = await db.textbooks.find(
        {"is_deleted": False}, {"_id": 0, "chunks": 0}
    ).sort("created_at", -1).to_list(500)
    owner_ids = list({t["owner_id"] for t in tbs})
    owners = await db.users.find(
        {"id": {"$in": owner_ids}}, {"_id": 0, "id": 1, "email": 1, "role": 1}
    ).to_list(len(owner_ids))
    by_id = {o["id"]: o for o in owners}
    out = []
    for t in tbs:
        owner = by_id.get(t["owner_id"], {})
        out.append({
            "id": t["id"],
            "original_filename": t["original_filename"],
            "subject": t["subject"],
            "class_name": t["class_name"],
            "status": t["status"],
            "topic_count": len(t.get("topics", [])),
            "chunk_count": t.get("chunk_count", 0),
            "is_shared": t.get("is_shared", False),
            "created_at": t["created_at"],
            "owner_id": t["owner_id"],
            "owner_email": owner.get("email", ""),
            "owner_role": owner.get("role", ""),
        })
    return out


@api_router.patch("/admin/textbooks/{textbook_id}/share")
async def admin_set_textbook_shared(
    textbook_id: str,
    is_shared: bool = Query(...),
    user: dict = Depends(get_current_user),
):
    require_admin(user)
    tb = await db.textbooks.find_one(
        {"id": textbook_id, "is_deleted": False}, {"_id": 0}
    )
    if not tb:
        raise HTTPException(status_code=404, detail="Textbook not found")
    await db.textbooks.update_one(
        {"id": textbook_id}, {"$set": {"is_shared": bool(is_shared)}}
    )
    return {"id": textbook_id, "is_shared": bool(is_shared)}


@api_router.get("/admin/papers")
async def admin_papers(user: dict = Depends(get_current_user)):
    require_admin(user)
    papers = await db.papers.find(
        {"is_deleted": False},
        {"_id": 0, "sections": 0, "topics": 0, "chunks": 0},
    ).sort("created_at", -1).to_list(500)
    owner_ids = list({p["owner_id"] for p in papers})
    owners = await db.users.find(
        {"id": {"$in": owner_ids}}, {"_id": 0, "id": 1, "email": 1}
    ).to_list(len(owner_ids))
    by_id = {o["id"]: o["email"] for o in owners}
    return [
        {
            "id": p["id"],
            "title": p.get("title", ""),
            "subject": p.get("subject", ""),
            "class_name": p.get("class_name", ""),
            "total_marks": p.get("total_marks", 0),
            "generation_status": p.get("generation_status", "ready"),
            "created_at": p.get("created_at", ""),
            "owner_id": p["owner_id"],
            "owner_email": by_id.get(p["owner_id"], ""),
        }
        for p in papers
    ]
