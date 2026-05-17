"""Phase 2: Competitive exam + RAG endpoints + Phase 3 PDF 600 dpi smoke."""
import os, time, uuid, io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://question-ai-10.preview.emergentagent.com").rstrip("/")
SEEDED_EXAM_ID = "a1392323-74fe-4139-8d4e-cd53be029e19"

TEACHER = ("pdftest@t.com", "pass123")
ADMIN = ("admin@bodhi.ai", "admin123")
STUDENT = ("student.smoke.1779011398@example.com", "pass123")


def _login(email, pwd):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def teacher_token():
    return _login(*TEACHER)


@pytest.fixture(scope="session")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="session")
def student_token():
    return _login(*STUDENT)


def H(t):
    return {"Authorization": f"Bearer {t}"}


# ---------- Exam CRUD + list visibility ----------
class TestExamCRUD:
    def test_student_cannot_create(self, student_token):
        r = requests.post(f"{BASE_URL}/api/competitive-exams", headers=H(student_token),
                          json={"name": "TEST_StudentTry", "description": "x", "is_shared": True}, timeout=20)
        assert r.status_code == 403

    def test_teacher_create_returns_id_name_shared(self, teacher_token):
        name = f"TEST_Exam_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE_URL}/api/competitive-exams", headers=H(teacher_token),
                          json={"name": name, "description": "test", "is_shared": False}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["name"] == name
        assert d["is_shared"] is False
        assert "id" in d
        pytest.created_exam_id = d["id"]

    def test_get_exam_has_topic_and_difficulty_counts_and_papers(self, teacher_token):
        r = requests.get(f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}", headers=H(teacher_token), timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["id"] == SEEDED_EXAM_ID
        assert "topic_counts" in d and isinstance(d["topic_counts"], dict)
        assert "difficulty_counts" in d
        for k in ("easy", "medium", "hard"):
            assert k in d["difficulty_counts"]
        assert isinstance(d.get("papers"), list)
        # 10 pre-seeded past questions in this exam
        total = sum(d["topic_counts"].values())
        assert total >= 10, f"expected >=10 indexed questions, got {total}"

    def test_list_student_only_sees_shared(self, student_token):
        r = requests.get(f"{BASE_URL}/api/competitive-exams", headers=H(student_token), timeout=20)
        assert r.status_code == 200
        exams = r.json()
        for e in exams:
            assert e["is_shared"] is True

    def test_list_teacher_sees_own_plus_shared(self, teacher_token):
        r = requests.get(f"{BASE_URL}/api/competitive-exams", headers=H(teacher_token), timeout=20)
        assert r.status_code == 200
        exams = r.json()
        # Should at least include the seeded JEE Main Test (shared)
        ids = [e["id"] for e in exams]
        assert SEEDED_EXAM_ID in ids

    def test_list_admin_sees_all(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/competitive-exams", headers=H(admin_token), timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- RAG preview ----------
class TestRAGPreview:
    def test_projectile_motion_returns_anchors(self, teacher_token):
        r = requests.get(
            f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}/rag-preview",
            params={"topic": "Projectile Motion", "k": 5},
            headers=H(teacher_token), timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert "anchors" in d and "distribution" in d
        for k in ("easy", "medium", "hard"):
            assert k in d["distribution"]
        anchors = d["anchors"]
        assert len(anchors) >= 2, f"expected >=2 anchors, got {len(anchors)}"
        # sorted by descending similarity
        scores = [a.get("_score", 0) for a in anchors]
        assert scores == sorted(scores, reverse=True), f"anchors not sorted desc: {scores}"
        # at least one projectile-tagged
        topics = [(a.get("topic") or "").lower() for a in anchors]
        assert any("projectile" in t for t in topics), f"no projectile-tagged: {topics}"

    def test_student_403(self, student_token):
        r = requests.get(
            f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}/rag-preview",
            params={"topic": "Kinematics", "k": 3},
            headers=H(student_token), timeout=20,
        )
        assert r.status_code == 403


# ---------- Past-paper upload + delete (using a tiny fake PDF; ingestion may end as extraction_empty) ----------
class TestPastPaperLifecycle:
    def test_upload_returns_ingesting_then_delete_decrements(self, teacher_token):
        # tiny but valid PDF
        pdf = (b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
               b"2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n"
               b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
               b"xref\n0 4\n0000000000 65535 f \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n0\n%%EOF")
        files = {"file": ("TEST_paper.pdf", io.BytesIO(pdf), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}/papers/upload",
            headers=H(teacher_token), files=files, timeout=60,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "ingesting"
        assert "id" in d
        paper_id = d["id"]
        # Poll a few times for terminal status
        terminal = {"ready", "failed", "extraction_empty"}
        final = None
        for _ in range(15):
            time.sleep(2)
            er = requests.get(f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}", headers=H(teacher_token), timeout=20)
            assert er.status_code == 200
            for p in er.json().get("papers", []):
                if p["id"] == paper_id and p["status"] in terminal:
                    final = p["status"]
                    break
            if final:
                break
        assert final in terminal, f"never reached terminal; last={final}"
        # Delete
        dr = requests.delete(
            f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}/papers/{paper_id}",
            headers=H(teacher_token), timeout=20,
        )
        assert dr.status_code == 200, dr.text
        # Verify tombstoned (not present in papers list)
        er2 = requests.get(f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}", headers=H(teacher_token), timeout=20)
        ids = [p["id"] for p in er2.json().get("papers", [])]
        assert paper_id not in ids

    def test_student_cannot_upload(self, student_token):
        files = {"file": ("TEST_x.pdf", io.BytesIO(b"%PDF-1.1\n%%EOF"), "application/pdf")}
        r = requests.post(
            f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}/papers/upload",
            headers=H(student_token), files=files, timeout=30,
        )
        assert r.status_code == 403


# ---------- Generate competitive paper (RAG) ----------
class TestGeneratePaper:
    def test_generate_kicks_off_and_reaches_ready(self, teacher_token):
        body = {
            "exam_id": SEEDED_EXAM_ID,
            "title": f"TEST_RAG_{uuid.uuid4().hex[:6]}",
            "topics": ["Projectile Motion", "Kinematics"],
            "difficulty": "medium",
            "question_count": 6,
            "duration_minutes": 30,
            "format_distribution": {"mcq": 100},
            "custom_instructions": "",
        }
        r = requests.post(
            f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}/generate-paper",
            headers=H(teacher_token), json=body, timeout=30,
        )
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["is_competitive"] is True
        assert p["competitive_exam_id"] == SEEDED_EXAM_ID
        assert p["generation_status"] == "pending"
        paper_id = p["id"]
        # Poll up to ~60s for status ready
        final = None
        for _ in range(30):
            time.sleep(2)
            gr = requests.get(f"{BASE_URL}/api/papers/{paper_id}", headers=H(teacher_token), timeout=20)
            if gr.status_code == 200:
                pd = gr.json()
                if pd.get("generation_status") in ("ready", "failed"):
                    final = pd
                    break
        assert final is not None, "paper never reached terminal"
        assert final["generation_status"] == "ready", f"failed: {final.get('generation_error')}"
        assert "rag_anchors_used" in final and final["rag_anchors_used"] > 0
        assert "rag_difficulty_distribution" in final
        # MCQ shape
        secs = final.get("sections") or []
        assert len(secs) >= 1
        seen_mcq = 0
        for s in secs:
            for q in s.get("questions", []):
                fmt = (q.get("format") or "").lower()
                if fmt == "mcq":
                    seen_mcq += 1
                    assert isinstance(q.get("options"), list) and len(q["options"]) == 4
                    assert isinstance(q.get("correct_option"), int)
                    assert 0 <= q["correct_option"] < 4
        assert seen_mcq >= 3, f"expected >=3 MCQs, got {seen_mcq}"
        pytest.gen_paper_id = paper_id

    def test_pdf_renders_for_competitive_paper(self, teacher_token):
        pid = getattr(pytest, "gen_paper_id", None)
        if not pid:
            pytest.skip("no paper id")
        r = requests.get(f"{BASE_URL}/api/papers/{pid}/pdf", headers=H(teacher_token), timeout=120)
        assert r.status_code == 200, r.status_code
        assert "application/pdf" in r.headers.get("content-type", "")
        assert len(r.content) > 5000  # at least 5KB

    def test_exam_id_mismatch_400(self, teacher_token):
        r = requests.post(
            f"{BASE_URL}/api/competitive-exams/{SEEDED_EXAM_ID}/generate-paper",
            headers=H(teacher_token),
            json={"exam_id": "different-id", "topics": ["X"], "question_count": 5, "duration_minutes": 10},
            timeout=20,
        )
        assert r.status_code == 400


# ---------- Existing teacher regression ----------
class TestRegression:
    def test_admin_overview(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/overview", headers=H(admin_token), timeout=20)
        assert r.status_code == 200

    def test_textbooks(self, teacher_token):
        r = requests.get(f"{BASE_URL}/api/textbooks", headers=H(teacher_token), timeout=20)
        assert r.status_code == 200
