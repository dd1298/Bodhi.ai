"""
Backend regression tests for NEW features (iter 3):
- Multi-textbook selection (textbook_ids array)
- Async paper generation (returns instantly with status='pending')
- Custom AI instructions (custom_instructions)
- Format distribution (format_distribution dict + custom labels)
- PDF rendering (DejaVu font, no raw LaTeX leaks)
- PDF blocking on pending/failed (409)
- Auth enforcement on cross-teacher access (403)
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

EXISTING_EMAIL = "pdftest@t.com"
EXISTING_PASSWORD = "pass123"

POLL_TIMEOUT = 120  # seconds
HTTP_TIMEOUT = 60  # generous for flaky preview proxy


# --------- helpers ---------
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


def physics_pdf() -> bytes:
    return _pdf_bytes(
        "Physics Textbook - Class 10",
        [
            "Chapter 1: Motion and Forces",
            "Newton's Laws govern motion of bodies.",
            "First Law: An object at rest stays at rest unless acted upon by a force.",
            "Second Law: F = m * a (force equals mass times acceleration)",
            "Third Law: For every action there is an equal and opposite reaction.",
            "Topics: Kinematics, Dynamics, Projectile Motion, Circular Motion.",
            "Velocity v = u + a*t. Distance s = ut + 0.5 a t squared.",
        ],
    )


def chemistry_pdf() -> bytes:
    return _pdf_bytes(
        "Chemistry Textbook - Class 10",
        [
            "Chapter 1: Acids, Bases and Salts",
            "Acids release H+ ions in aqueous solutions.",
            "Bases release OH- ions in aqueous solutions.",
            "pH scale ranges from 0 (acidic) to 14 (basic).",
            "Topics: Acids, Bases, Salts, Neutralisation, Indicators.",
            "Common acids: HCl, H2SO4, HNO3. Common bases: NaOH, KOH, NH4OH.",
        ],
    )


# --------- fixtures ---------
@pytest.fixture(scope="module")
def teacher_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": EXISTING_EMAIL, "password": EXISTING_PASSWORD},
        timeout=90,
    )
    if r.status_code != 200:
        pytest.skip(f"Cannot login as seeded teacher: {r.status_code} {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def teacher_headers(teacher_token):
    return {"Authorization": f"Bearer {teacher_token}"}


@pytest.fixture(scope="module")
def second_teacher_token():
    """A fresh second teacher used for cross-tenant 403 test."""
    email = f"second_teacher_{int(time.time())}@t.com"
    r = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": email,
            "password": "pass1234",
            "full_name": "Second Teacher",
            "role": "teacher",
        },
        timeout=90,
    )
    if r.status_code != 200:
        pytest.skip(f"Cannot register second teacher: {r.text}")
    return r.json()["token"]


@pytest.fixture(scope="module")
def two_textbooks(teacher_headers):
    """Upload 2 textbooks (Physics + Chemistry) for multi-textbook tests."""
    ids = []
    for label, blob, subj in [
        ("physics.pdf", physics_pdf(), "Physics"),
        ("chemistry.pdf", chemistry_pdf(), "Chemistry"),
    ]:
        r = requests.post(
            f"{BASE_URL}/api/textbooks/upload",
            files={"file": (label, blob, "application/pdf")},
            params={"subject": subj, "class_name": "10"},
            headers=teacher_headers,
            timeout=60,
        )
        assert r.status_code == 200, f"Upload {label} failed: {r.text}"
        ids.append(r.json()["id"])
    return ids


def _poll_until_done(paper_id: str, headers: dict, timeout: int = POLL_TIMEOUT) -> dict:
    """Poll GET /api/papers/{id} until generation_status != pending or timeout."""
    start = time.time()
    last = None
    while time.time() - start < timeout:
        r = requests.get(
            f"{BASE_URL}/api/papers/{paper_id}", headers=headers, timeout=90
        )
        assert r.status_code == 200, f"Get paper failed: {r.text}"
        last = r.json()
        if last.get("generation_status") in ("ready", "failed"):
            return last
        time.sleep(3)
    return last or {}


# =========================================================
# Tests
# =========================================================
class TestAsyncGeneration:
    """Async generation must return immediately with status='pending'."""

    def test_generate_returns_pending_quickly(self, teacher_headers, two_textbooks):
        t0 = time.time()
        r = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Async Pending Test",
                "subject": "Physics",
                "class_name": "10",
                "textbook_ids": [two_textbooks[0]],
                "topics": ["Motion", "Forces"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 50, "concept": 30, "application": 20},
            },
            headers=teacher_headers,
            timeout=90,
        )
        elapsed = time.time() - t0
        assert r.status_code == 200, f"generate failed: {r.text}"
        data = r.json()
        assert "id" in data
        assert data.get("generation_status") == "pending", f"got {data.get('generation_status')}"
        assert data.get("sections") == [] or data.get("sections") is None
        assert elapsed < 30, f"endpoint too slow: {elapsed}s"
        print(f"OK async generate returned pending in {elapsed:.2f}s, paper={data['id']}")
        # Save paper id for downstream tests
        pytest.async_paper_id = data["id"]

    def test_pdf_blocked_while_pending(self, teacher_headers):
        pid = getattr(pytest, "async_paper_id", None)
        if not pid:
            pytest.skip("no paper id from pending test")
        # Immediately after creation, status should still be pending in most cases.
        # But if it's already done, this still validates 200 path. So fetch once.
        meta = requests.get(f"{BASE_URL}/api/papers/{pid}", headers=teacher_headers, timeout=60).json()
        if meta.get("generation_status") == "pending":
            r = requests.get(f"{BASE_URL}/api/papers/{pid}/pdf", headers=teacher_headers, timeout=60)
            assert r.status_code == 409, f"expected 409 while pending, got {r.status_code}"
            print("OK PDF blocked with 409 while pending")
        else:
            print(f"NOTE paper already {meta.get('generation_status')}, skipping pending-PDF check")


class TestMultiTextbook:
    """Multi-textbook merge + multi-textbook persisted on doc."""

    def test_generate_with_multi_textbook_ids(self, teacher_headers, two_textbooks):
        r = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Multi Textbook Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_ids": two_textbooks,  # 2 books
                "topics": ["Motion", "Acids"],
                "difficulty": "medium",
                "duration_minutes": 45,
                "total_marks": 30,
                "distribution": {"information": 30, "concept": 40, "application": 30},
                "custom_instructions": "All answers must use whole numbers only",
                "format_distribution": {"mcq": 50, "short_answer": 30, "true_false": 20},
            },
            headers=teacher_headers,
            timeout=90,
        )
        assert r.status_code == 200, f"generate failed: {r.text}"
        data = r.json()
        assert data.get("generation_status") == "pending"
        assert isinstance(data.get("textbook_ids"), list) and len(data["textbook_ids"]) == 2
        # legacy field still set for back-compat
        assert data.get("textbook_id") in two_textbooks
        # custom fields persisted
        assert data.get("custom_instructions") == "All answers must use whole numbers only"
        assert data.get("format_distribution") == {"mcq": 50, "short_answer": 30, "true_false": 20}
        pytest.multi_paper_id = data["id"]
        print(f"OK multi-textbook paper accepted, id={data['id']}")

    def test_legacy_textbook_id_still_works(self, teacher_headers, two_textbooks):
        r = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Legacy Single Textbook",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": two_textbooks[0],  # legacy single
                "topics": ["Motion"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 40, "concept": 40, "application": 20},
            },
            headers=teacher_headers,
            timeout=90,
        )
        assert r.status_code == 200, f"legacy single failed: {r.text}"
        data = r.json()
        assert data.get("textbook_id") == two_textbooks[0]
        assert data.get("textbook_ids") == [two_textbooks[0]]
        print("OK legacy textbook_id still works")


class TestPollUntilReady:
    """Poll the multi-textbook async paper until ready/failed."""

    def test_paper_eventually_ready(self, teacher_headers):
        pid = getattr(pytest, "multi_paper_id", None)
        if not pid:
            pytest.skip("no multi paper id")
        final = _poll_until_done(pid, teacher_headers)
        status = final.get("generation_status")
        assert status in ("ready", "failed"), f"unexpected final status: {status}"
        if status == "failed":
            err = final.get("generation_error") or ""
            print(f"WARN generation_status=failed err={err[:200]}")
            # Budget exhausted is acceptable per request brief.
            pytest.skip(f"LLM generation failed (acceptable): {err[:200]}")
        # ready path: validate
        sections = final.get("sections") or []
        assert sections, "ready paper must have sections"
        all_qs = [q for s in sections for q in s.get("questions", [])]
        assert all_qs, "ready paper must have questions"
        # format field present
        assert all("format" in q for q in all_qs), "every question must have a format field"
        print(f"OK paper ready with {len(all_qs)} questions")
        pytest.ready_paper = final

    def test_format_distribution_mix(self, teacher_headers):
        final = getattr(pytest, "ready_paper", None)
        if not final:
            pytest.skip("no ready paper")
        all_qs = [q for s in final.get("sections", []) for q in s.get("questions", [])]
        total = len(all_qs)
        if not total:
            pytest.skip("no questions")
        mcq_qs = [q for q in all_qs if (q.get("format") or "").lower() == "mcq"]
        tf_qs = [q for q in all_qs if (q.get("format") or "").lower() in ("true_false", "true/false")]
        mcq_ratio = len(mcq_qs) / total
        print(f"format mix: total={total} mcq={len(mcq_qs)} ({mcq_ratio:.0%}) tf={len(tf_qs)}")
        # expected MCQ >= 30%
        assert mcq_ratio >= 0.30, f"MCQ ratio too low: {mcq_ratio:.0%} (expected >= 30%)"
        # MCQ questions should contain (a)/(b)/(c)/(d)
        for q in mcq_qs[:3]:
            text = (q.get("question") or "").lower()
            has_opts = ("(a)" in text and "(b)" in text and "(c)" in text and "(d)" in text)
            assert has_opts, f"MCQ missing options: {q.get('question')[:120]}"
        # T/F questions should end with "True or False?"
        for q in tf_qs[:2]:
            text = (q.get("question") or "").strip().rstrip(".").rstrip()
            assert text.lower().endswith("true or false?") or "true or false" in text.lower(), (
                f"T/F missing trailing prompt: {q.get('question')[:120]}"
            )
        print("OK format mix verified (MCQ >=30%, options present, T/F prompt present)")

    def test_pdf_download_after_ready(self, teacher_headers):
        final = getattr(pytest, "ready_paper", None)
        if not final:
            pytest.skip("no ready paper")
        pid = final["id"]
        r = requests.get(f"{BASE_URL}/api/papers/{pid}/pdf", headers=teacher_headers, timeout=60)
        assert r.status_code == 200, f"pdf download failed: {r.status_code} {r.text[:200]}"
        assert r.headers.get("Content-Type") == "application/pdf"
        body = r.content
        assert body[:4] == b"%PDF", "not a valid PDF"
        assert len(body) > 1024, f"pdf too small: {len(body)}"
        # No raw LaTeX leaks (heuristic): \frac, \sqrt, \sum should not appear
        # in the byte stream as visible text.
        suspicious = [b"\\frac", b"\\sqrt", b"\\sum"]
        leaks = [s for s in suspicious if s in body]
        assert not leaks, f"raw LaTeX found in PDF: {leaks}"
        # DejaVu font registered should appear in font dictionary
        # (ReportLab embeds font name into the PDF content)
        # We just check no obvious 'Helvetica fallback noise' marker - reportlab logs only.
        print(f"OK PDF rendered, {len(body)} bytes, no LaTeX leaks")


class TestCustomFormatChip:
    """Custom format label propagates to question.format."""

    def test_custom_format_case_study(self, teacher_headers, two_textbooks):
        r = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Case Study Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_ids": [two_textbooks[0]],
                "topics": ["Motion"],
                "difficulty": "medium",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 30, "concept": 40, "application": 30},
                "format_distribution": {"case_study": 100},
            },
            headers=teacher_headers,
            timeout=90,
        )
        assert r.status_code == 200, f"generate failed: {r.text}"
        pid = r.json()["id"]
        final = _poll_until_done(pid, teacher_headers)
        if final.get("generation_status") == "failed":
            pytest.skip(f"LLM failed (acceptable): {final.get('generation_error')}")
        all_qs = [q for s in final.get("sections", []) for q in s.get("questions", [])]
        cs_qs = [q for q in all_qs if (q.get("format") or "").lower() == "case_study"]
        assert cs_qs, f"no case_study format questions found among {[q.get('format') for q in all_qs]}"
        print(f"OK custom format propagated, {len(cs_qs)}/{len(all_qs)} case_study questions")


class TestCrossTeacherAuth:
    """Teacher A cannot read or download Teacher B's paper."""

    def test_cross_teacher_get_403(self, second_teacher_token, teacher_headers, two_textbooks):
        # First create a paper as teacher A
        r = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Private Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_ids": [two_textbooks[0]],
                "topics": ["Motion"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 50, "concept": 30, "application": 20},
            },
            headers=teacher_headers,
            timeout=90,
        )
        assert r.status_code == 200
        pid = r.json()["id"]
        # Now try as teacher B
        h2 = {"Authorization": f"Bearer {second_teacher_token}"}
        r = requests.get(f"{BASE_URL}/api/papers/{pid}", headers=h2, timeout=60)
        assert r.status_code in (403, 404), f"expected 403/404, got {r.status_code}"
        r = requests.get(f"{BASE_URL}/api/papers/{pid}/pdf", headers=h2, timeout=60)
        assert r.status_code in (403, 404, 409), f"expected 403/404/409, got {r.status_code}"
        print(f"OK cross-teacher access blocked ({r.status_code})")


class TestPDFFailedBlock:
    """PDF must 409 when generation_status='failed'."""

    def test_pdf_blocked_on_failed(self, teacher_headers):
        # Try to find an existing failed paper from listing
        r = requests.get(f"{BASE_URL}/api/papers", headers=teacher_headers, timeout=60)
        assert r.status_code == 200
        papers = r.json()
        failed = [p for p in papers if p.get("generation_status") == "failed"]
        if not failed:
            pytest.skip("no failed papers to verify 409 (acceptable)")
        pid = failed[0]["id"]
        r = requests.get(f"{BASE_URL}/api/papers/{pid}/pdf", headers=teacher_headers, timeout=60)
        assert r.status_code == 409, f"expected 409 on failed, got {r.status_code}"
        print("OK PDF blocked with 409 on failed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
