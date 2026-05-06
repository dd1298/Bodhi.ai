"""
Backend tests for P1 Admin Dashboard (iteration 4):
- Admin seed login
- /api/admin/overview, /users, /textbooks, /papers (admin only, non-admin 403)
- /api/admin/textbooks/{id}/share toggle + idempotency
- Shared textbook visibility for non-owner teacher
- Shared textbook usable by non-owner teacher in /papers/generate
- Upload is_shared flag ignored for teacher, honored for admin
- Admin can reindex/delete non-owned textbooks
"""
import os
import io
import time
import pytest
import requests
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@bodhi.ai"
ADMIN_PASSWORD = "admin123"
TEACHER_EMAIL = "pdftest@t.com"
TEACHER_PASSWORD = "pass123"

HTTP_TIMEOUT = 90


def _pdf_bytes(title: str, lines: list) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 760
    c.drawString(80, y, title)
    y -= 24
    for ln in lines:
        c.drawString(80, y, ln)
        y -= 18
    c.save()
    return buf.getvalue()


def _dummy_pdf() -> bytes:
    return _pdf_bytes(
        "Shared Science Reference",
        [
            "Chapter 1: Scientific Method",
            "Observation, hypothesis, experimentation, conclusion.",
            "Topics: Scientific Method, Units, Measurement.",
            "This textbook is used for testing shared-library access.",
        ],
    )


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=HTTP_TIMEOUT,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("user", {}).get("role") == "admin", f"role not admin: {data}"
    return data["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def teacher_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEACHER_EMAIL, "password": TEACHER_PASSWORD},
        timeout=HTTP_TIMEOUT,
    )
    assert r.status_code == 200, f"teacher login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def teacher_headers(teacher_token):
    return {"Authorization": f"Bearer {teacher_token}"}


@pytest.fixture(scope="module")
def admin_owned_textbook(admin_headers):
    """Admin uploads a textbook NOT owned by the teacher, used for share tests."""
    r = requests.post(
        f"{BASE_URL}/api/textbooks/upload",
        files={"file": ("TEST_admin_shared.pdf", _dummy_pdf(), "application/pdf")},
        params={"subject": "Science", "class_name": "10"},
        headers=admin_headers,
        timeout=HTTP_TIMEOUT,
    )
    assert r.status_code == 200, f"admin upload failed: {r.text}"
    data = r.json()
    # Wait briefly for ingestion status
    for _ in range(30):
        m = requests.get(
            f"{BASE_URL}/api/textbooks/{data['id']}",
            headers=admin_headers,
            timeout=HTTP_TIMEOUT,
        )
        if m.status_code == 200 and m.json().get("status") == "ready":
            return data["id"]
        time.sleep(2)
    return data["id"]  # proceed even if status not ready


# =========================================================
# Auth seed
# =========================================================
class TestAdminSeed:
    def test_admin_login_role(self):
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user"]["role"] == "admin"
        assert data["user"]["email"] == ADMIN_EMAIL
        assert isinstance(data.get("token"), str) and len(data["token"]) > 10


# =========================================================
# Admin RBAC endpoints
# =========================================================
class TestAdminOverview:
    def test_overview_returns_counts(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/overview", headers=admin_headers, timeout=HTTP_TIMEOUT
        )
        assert r.status_code == 200
        d = r.json()
        for k in (
            "teachers",
            "admins",
            "textbooks_total",
            "textbooks_shared",
            "papers_total",
            "papers_pending",
            "papers_failed",
        ):
            assert k in d, f"missing key {k}"
            assert isinstance(d[k], int)
        assert d["admins"] >= 1

    def test_overview_teacher_403(self, teacher_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/overview", headers=teacher_headers, timeout=HTTP_TIMEOUT
        )
        assert r.status_code == 403


class TestAdminUsers:
    def test_users_list_no_password_hash(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/users", headers=admin_headers, timeout=HTTP_TIMEOUT
        )
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list) and len(users) >= 1
        for u in users:
            assert "password_hash" not in u, "password_hash leaked!"
            assert "email" in u and "role" in u
            assert "textbook_count" in u and "paper_count" in u

    def test_users_teacher_403(self, teacher_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/users", headers=teacher_headers, timeout=HTTP_TIMEOUT
        )
        assert r.status_code == 403


class TestAdminTextbooks:
    def test_textbooks_lists_all(self, admin_headers, admin_owned_textbook):
        r = requests.get(
            f"{BASE_URL}/api/admin/textbooks",
            headers=admin_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        tbs = r.json()
        assert isinstance(tbs, list)
        assert any(t["id"] == admin_owned_textbook for t in tbs)
        for t in tbs:
            assert "owner_email" in t and "is_shared" in t

    def test_textbooks_teacher_403(self, teacher_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/textbooks",
            headers=teacher_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 403


class TestAdminPapers:
    def test_papers_lists_all_with_owner(self, admin_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/papers", headers=admin_headers, timeout=HTTP_TIMEOUT
        )
        assert r.status_code == 200
        papers = r.json()
        assert isinstance(papers, list)
        if papers:
            assert "owner_email" in papers[0]

    def test_papers_teacher_403(self, teacher_headers):
        r = requests.get(
            f"{BASE_URL}/api/admin/papers", headers=teacher_headers, timeout=HTTP_TIMEOUT
        )
        assert r.status_code == 403


# =========================================================
# Sharing logic
# =========================================================
class TestShareTextbook:
    def test_teacher_cannot_see_admin_book_before_share(
        self, admin_owned_textbook, teacher_headers
    ):
        r = requests.get(
            f"{BASE_URL}/api/textbooks", headers=teacher_headers, timeout=HTTP_TIMEOUT
        )
        assert r.status_code == 200
        ids = [t["id"] for t in r.json()]
        assert admin_owned_textbook not in ids, "teacher should NOT see unshared admin book"

        # And direct GET is 403
        r = requests.get(
            f"{BASE_URL}/api/textbooks/{admin_owned_textbook}",
            headers=teacher_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code in (403, 404)

    def test_admin_share_toggle_idempotent(self, admin_headers, admin_owned_textbook):
        # share=true
        r = requests.patch(
            f"{BASE_URL}/api/admin/textbooks/{admin_owned_textbook}/share",
            params={"is_shared": "true"},
            headers=admin_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        assert r.json()["is_shared"] is True
        # call again - idempotent
        r2 = requests.patch(
            f"{BASE_URL}/api/admin/textbooks/{admin_owned_textbook}/share",
            params={"is_shared": "true"},
            headers=admin_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r2.status_code == 200
        assert r2.json()["is_shared"] is True

    def test_share_non_admin_403(self, teacher_headers, admin_owned_textbook):
        r = requests.patch(
            f"{BASE_URL}/api/admin/textbooks/{admin_owned_textbook}/share",
            params={"is_shared": "true"},
            headers=teacher_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 403

    def test_teacher_sees_shared_book_readonly(
        self, admin_owned_textbook, teacher_headers
    ):
        r = requests.get(
            f"{BASE_URL}/api/textbooks", headers=teacher_headers, timeout=HTTP_TIMEOUT
        )
        assert r.status_code == 200
        tbs = r.json()
        match = [t for t in tbs if t["id"] == admin_owned_textbook]
        assert match, "teacher should see shared admin book"
        t = match[0]
        assert t.get("is_shared") is True
        assert t.get("is_owned") is False

        # GET single now 200
        r = requests.get(
            f"{BASE_URL}/api/textbooks/{admin_owned_textbook}",
            headers=teacher_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200

    def test_teacher_generate_with_shared_book(
        self, admin_owned_textbook, teacher_headers
    ):
        # Must be shared at this point
        r = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Shared-book paper",
                "subject": "Science",
                "class_name": "10",
                "textbook_ids": [admin_owned_textbook],
                "topics": ["Scientific Method"],
                "difficulty": "easy",
                "duration_minutes": 20,
                "total_marks": 10,
                "distribution": {"information": 50, "concept": 30, "application": 20},
            },
            headers=teacher_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200, f"teacher should be able to use shared book: {r.status_code} {r.text[:200]}"

    def test_unshare_blocks_generate(
        self, admin_headers, admin_owned_textbook, teacher_headers
    ):
        # Unshare
        r = requests.patch(
            f"{BASE_URL}/api/admin/textbooks/{admin_owned_textbook}/share",
            params={"is_shared": "false"},
            headers=admin_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        assert r.json()["is_shared"] is False

        # Teacher can no longer use it
        r = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Post-unshare paper",
                "subject": "Science",
                "class_name": "10",
                "textbook_ids": [admin_owned_textbook],
                "topics": ["Scientific Method"],
                "difficulty": "easy",
                "duration_minutes": 20,
                "total_marks": 10,
                "distribution": {"information": 50, "concept": 30, "application": 20},
            },
            headers=teacher_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code in (403, 404), f"expected 403/404 after unshare, got {r.status_code}"


# =========================================================
# Upload is_shared flag semantics
# =========================================================
class TestUploadIsSharedFlag:
    def test_teacher_cannot_self_share_upload(self, teacher_headers):
        r = requests.post(
            f"{BASE_URL}/api/textbooks/upload",
            files={"file": ("TEST_teacher_try_share.pdf", _dummy_pdf(), "application/pdf")},
            params={"subject": "Science", "class_name": "10", "is_shared": "true"},
            headers=teacher_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        tid = r.json()["id"]
        # Verify NOT shared
        r = requests.get(
            f"{BASE_URL}/api/textbooks/{tid}",
            headers=teacher_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        assert r.json().get("is_shared") is False, "teacher must not be able to self-share"

    def test_admin_upload_is_shared_true(self, admin_headers):
        r = requests.post(
            f"{BASE_URL}/api/textbooks/upload",
            files={"file": ("TEST_admin_upload_shared.pdf", _dummy_pdf(), "application/pdf")},
            params={"subject": "Science", "class_name": "10", "is_shared": "true"},
            headers=admin_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        tid = r.json()["id"]
        r = requests.get(
            f"{BASE_URL}/api/admin/textbooks",
            headers=admin_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        match = [t for t in r.json() if t["id"] == tid]
        assert match and match[0]["is_shared"] is True


# =========================================================
# Admin can manage non-owned textbooks
# =========================================================
class TestAdminManageNonOwned:
    def test_admin_reindex_teacher_book(self, admin_headers, teacher_headers):
        # teacher uploads a book
        r = requests.post(
            f"{BASE_URL}/api/textbooks/upload",
            files={"file": ("TEST_teacher_owned.pdf", _dummy_pdf(), "application/pdf")},
            params={"subject": "Science", "class_name": "10"},
            headers=teacher_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code == 200
        tid = r.json()["id"]
        # admin reindex
        r = requests.post(
            f"{BASE_URL}/api/textbooks/{tid}/reindex",
            headers=admin_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code in (200, 202), f"admin reindex failed: {r.status_code} {r.text[:200]}"
        # admin delete
        r = requests.delete(
            f"{BASE_URL}/api/textbooks/{tid}",
            headers=admin_headers,
            timeout=HTTP_TIMEOUT,
        )
        assert r.status_code in (200, 204), f"admin delete failed: {r.status_code} {r.text[:200]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
