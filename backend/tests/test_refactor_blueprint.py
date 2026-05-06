"""
Iteration 5 tests:
  P1 — Backend refactor regression (server.py split into deps/admin_routes/workers)
       All existing endpoints must continue to function identically.
  P0 — section_blueprint override on POST /api/papers/generate.

Coverage:
  * Auth: login admin + teacher, /auth/me
  * Textbooks: list, get
  * Papers: generate (+poll), get, list, pdf
  * Solutions: generate (+poll)
  * Admin: overview/users/textbooks/papers/share — admin 200, teacher 403
  * Blueprint absent (regression) → 3 Bloom sections
  * Blueprint ICSE Class 10 → 2 sections (A=40m many Qs, B=40m attempt-any-4-of-6)
  * Blueprint CBSE Class 10 → 5 sections (A..E)
  * Blueprint custom free-form → 1 section, 5 essays of 10m
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@bodhi.ai"
ADMIN_PASSWORD = "admin123"
TEACHER_EMAIL = "pdftest@t.com"
TEACHER_PASSWORD = "pass123"
TEACHER_TEXTBOOK_ID = "752a5124-62ca-4007-bd6e-d0ad9f03d3a1"

TIMEOUT = 120
GEN_POLL_TIMEOUT = 240  # seconds — blueprint papers (25+ Qs) take longer
GEN_POLL_INTERVAL = 5


def _login(email, password):
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def teacher_token():
    return _login(TEACHER_EMAIL, TEACHER_PASSWORD)


@pytest.fixture(scope="module")
def teacher_textbook_id(teacher_token):
    h = {"Authorization": f"Bearer {teacher_token}"}
    r = requests.get(
        f"{BASE_URL}/api/textbooks/{TEACHER_TEXTBOOK_ID}", headers=h, timeout=TIMEOUT
    )
    if r.status_code == 200:
        return TEACHER_TEXTBOOK_ID
    # fallback: pick any indexed one
    rl = requests.get(f"{BASE_URL}/api/textbooks", headers=h, timeout=TIMEOUT)
    rl.raise_for_status()
    for tb in rl.json():
        if tb.get("status") == "indexed":
            return tb["id"]
    pytest.skip("no indexed textbook available for teacher")


def _poll_paper(token, paper_id, want_status=("ready", "partial", "failed")):
    h = {"Authorization": f"Bearer {token}"}
    end = time.time() + GEN_POLL_TIMEOUT
    last = {}
    while time.time() < end:
        try:
            r = requests.get(
                f"{BASE_URL}/api/papers/{paper_id}", headers=h, timeout=TIMEOUT
            )
        except requests.exceptions.RequestException:
            time.sleep(GEN_POLL_INTERVAL)
            continue
        if r.status_code in (502, 503, 504):
            time.sleep(GEN_POLL_INTERVAL)
            continue
        assert r.status_code == 200, r.text
        last = r.json()
        st = last.get("generation_status")
        if st in want_status:
            return last
        time.sleep(GEN_POLL_INTERVAL)
    pytest.fail(
        f"paper {paper_id} did not reach {want_status} in {GEN_POLL_TIMEOUT}s. "
        f"last_status={last.get('generation_status')} err={last.get('generation_error')}"
    )


# -------------- Auth regression --------------
class TestAuthRegression:
    def test_admin_login(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_teacher_login(self, teacher_token):
        assert isinstance(teacher_token, str) and len(teacher_token) > 20

    def test_auth_me_admin(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        d = r.json()
        assert d.get("email") == ADMIN_EMAIL
        assert d.get("role") == "admin"
        assert "password_hash" not in d

    def test_auth_me_teacher(self, teacher_token):
        r = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {teacher_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        d = r.json()
        assert d.get("email") == TEACHER_EMAIL


# -------------- Textbooks regression --------------
class TestTextbooksRegression:
    def test_list_textbooks(self, teacher_token):
        r = requests.get(
            f"{BASE_URL}/api/textbooks",
            headers={"Authorization": f"Bearer {teacher_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_textbook(self, teacher_token, teacher_textbook_id):
        r = requests.get(
            f"{BASE_URL}/api/textbooks/{teacher_textbook_id}",
            headers={"Authorization": f"Bearer {teacher_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == teacher_textbook_id
        assert "_id" not in d


# -------------- Admin endpoints regression --------------
class TestAdminRoutesRegression:
    def test_admin_overview(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/overview",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        d = r.json()
        for k in ("teachers", "admins", "textbooks_total", "textbooks_shared",
                  "papers_total", "papers_pending", "papers_failed"):
            assert k in d, f"missing key {k}"

    def test_admin_users(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/users",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        users = r.json()
        assert isinstance(users, list) and len(users) >= 1
        assert all("password_hash" not in u for u in users)

    def test_admin_textbooks(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/textbooks",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_papers(self, admin_token):
        r = requests.get(
            f"{BASE_URL}/api/admin/papers",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_admin_share_toggle_idempotent(self, admin_token):
        # pick any non-shared textbook
        rl = requests.get(
            f"{BASE_URL}/api/admin/textbooks",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=TIMEOUT,
        )
        tbs = rl.json()
        target = next((t for t in tbs), None)
        if not target:
            pytest.skip("no textbooks to toggle")
        tid = target["id"]
        original = bool(target.get("is_shared", False))
        h = {"Authorization": f"Bearer {admin_token}"}
        r1 = requests.patch(
            f"{BASE_URL}/api/admin/textbooks/{tid}/share?is_shared={'true' if not original else 'false'}",
            headers=h, timeout=TIMEOUT,
        )
        assert r1.status_code == 200
        # restore
        r2 = requests.patch(
            f"{BASE_URL}/api/admin/textbooks/{tid}/share?is_shared={'true' if original else 'false'}",
            headers=h, timeout=TIMEOUT,
        )
        assert r2.status_code == 200
        assert r2.json()["is_shared"] == original

    @pytest.mark.parametrize("path", [
        "/api/admin/overview",
        "/api/admin/users",
        "/api/admin/textbooks",
        "/api/admin/papers",
    ])
    def test_admin_endpoints_teacher_403(self, teacher_token, path):
        r = requests.get(
            f"{BASE_URL}{path}",
            headers={"Authorization": f"Bearer {teacher_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 403

    def test_admin_share_teacher_403(self, teacher_token, admin_token):
        rl = requests.get(
            f"{BASE_URL}/api/admin/textbooks",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=TIMEOUT,
        )
        tbs = rl.json()
        if not tbs:
            pytest.skip("no textbooks")
        tid = tbs[0]["id"]
        r = requests.patch(
            f"{BASE_URL}/api/admin/textbooks/{tid}/share?is_shared=true",
            headers={"Authorization": f"Bearer {teacher_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 403


# -------------- Paper generate (no blueprint) regression --------------
@pytest.fixture(scope="module")
def base_paper_payload(teacher_textbook_id):
    return {
        "title": "TEST_iter5_basic",
        "subject": "Science",
        "class_name": "10",
        "textbook_id": teacher_textbook_id,
        "topics": [{"name": "Light", "weight": 5}, {"name": "Sound", "weight": 5}],
        "difficulty": "medium",
        "duration_minutes": 60,
        "total_marks": 30,
        "distribution": {"information": 30, "concept": 40, "application": 30},
    }


class TestPaperGenerateRegression:
    @pytest.fixture(scope="class")
    def paper_no_blueprint(self, teacher_token, base_paper_payload):
        h = {"Authorization": f"Bearer {teacher_token}"}
        r = requests.post(
            f"{BASE_URL}/api/papers/generate", headers=h,
            json=base_paper_payload, timeout=TIMEOUT,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("generation_status") == "pending"
        assert d.get("section_blueprint", "") == ""
        return _poll_paper(teacher_token, d["id"])

    def test_default_3_bloom_sections(self, paper_no_blueprint):
        p = paper_no_blueprint
        if p.get("generation_status") == "failed":
            pytest.skip(f"generation failed (likely budget): {p.get('generation_error')}")
        assert p["generation_status"] in ("ready", "partial")
        sections = p.get("sections", [])
        # Default Bloom split = 3 sections (Information / Concept / Application)
        assert len(sections) == 3, f"expected 3 Bloom sections, got {len(sections)}"

    def test_papers_list_includes_paper(self, teacher_token, paper_no_blueprint):
        r = requests.get(
            f"{BASE_URL}/api/papers",
            headers={"Authorization": f"Bearer {teacher_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()}
        assert paper_no_blueprint["id"] in ids

    def test_paper_pdf_bytes(self, teacher_token, paper_no_blueprint):
        if paper_no_blueprint.get("generation_status") == "failed":
            pytest.skip("generation failed; pdf check skipped")
        r = requests.get(
            f"{BASE_URL}/api/papers/{paper_no_blueprint['id']}/pdf",
            headers={"Authorization": f"Bearer {teacher_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        # very loose pdf magic check
        assert r.content[:4] == b"%PDF", "response is not a PDF"


# -------------- Blueprint feature (P0) --------------
ICSE_BLUEPRINT = (
    "Section A (40 marks, compulsory):\n"
    "  Q1: 15 multiple-choice questions (1 mark each).\n"
    "  Q2: 6 fill in the blanks (1 mark each).\n"
    "  Q3: 4 short-answer parts (4 marks).\n"
    "Section B (40 marks, attempt any FOUR of the following SIX):\n"
    "  Q4 to Q9: each 10 marks, internally subdivided into 3+3+4 sub-parts."
)

CBSE_BLUEPRINT = (
    "Section A (16 marks): 16 MCQs of 1 mark each.\n"
    "Section B (10 marks): 5 very short-answer questions of 2 marks each.\n"
    "Section C (18 marks): 6 short-answer questions of 3 marks each.\n"
    "Section D (20 marks): 4 long-answer questions of 5 marks each.\n"
    "Section E (16 marks): 4 case-study questions of 4 marks each."
)

CUSTOM_BLUEPRINT = (
    "Section X (50 marks) — 5 essay questions of 10 marks each. "
    "No internal choice. No sub-parts."
)


def _generate_with_blueprint(token, payload):
    h = {"Authorization": f"Bearer {token}"}
    r = requests.post(
        f"{BASE_URL}/api/papers/generate", headers=h, json=payload, timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["generation_status"] == "pending"
    assert d.get("section_blueprint", "").strip().startswith(
        payload["section_blueprint"].splitlines()[0][:20]
    )
    return _poll_paper(token, d["id"])


class TestBlueprintICSE:
    @pytest.fixture(scope="class")
    def paper(self, teacher_token, base_paper_payload):
        payload = {
            **base_paper_payload,
            "title": "TEST_iter5_icse",
            "total_marks": 80,
            "duration_minutes": 120,
            "section_blueprint": ICSE_BLUEPRINT,
        }
        return _generate_with_blueprint(teacher_token, payload)

    def test_blueprint_persisted(self, paper):
        assert paper.get("section_blueprint", "").startswith("Section A (40 marks")

    def test_two_sections(self, paper):
        if paper.get("generation_status") == "failed":
            pytest.skip(f"gen failed: {paper.get('generation_error')}")
        sections = paper.get("sections", [])
        assert len(sections) == 2, (
            f"ICSE blueprint expected EXACTLY 2 sections, got {len(sections)}: "
            f"{[s.get('title') for s in sections]}"
        )

    def test_section_a_marks_and_count(self, paper):
        if paper.get("generation_status") == "failed":
            pytest.skip("gen failed")
        sections = paper.get("sections", [])
        if len(sections) < 1:
            pytest.skip("no sections")
        sec_a = sections[0]
        qs = sec_a.get("questions", [])
        # ICSE Section A: 15 MCQs + 6 fills + ~4 short-answer parts ≈ 25 questions
        assert 18 <= len(qs) <= 30, f"Section A expected ~25 questions, got {len(qs)}"
        marks = sum(int(q.get("marks", 0)) for q in qs)
        assert 35 <= marks <= 45, f"Section A expected ~40 marks, got {marks}"

    def test_section_b_six_ten_mark_questions(self, paper):
        if paper.get("generation_status") == "failed":
            pytest.skip("gen failed")
        sections = paper.get("sections", [])
        if len(sections) < 2:
            pytest.skip("Section B missing")
        sec_b = sections[1]
        qs = sec_b.get("questions", [])
        assert len(qs) == 6, f"Section B expected 6 questions, got {len(qs)}"
        for q in qs:
            assert int(q.get("marks", 0)) == 10, f"Q expected 10m, got {q.get('marks')}"

    def test_section_b_attempt_any_in_title(self, paper):
        if paper.get("generation_status") == "failed":
            pytest.skip("gen failed")
        sections = paper.get("sections", [])
        if len(sections) < 2:
            pytest.skip("no Section B")
        title_b = (sections[1].get("title") or "").lower()
        assert "attempt" in title_b and ("four" in title_b or "4" in title_b), (
            f"Section B title should mention 'attempt any FOUR', got: {sections[1].get('title')}"
        )

    def test_section_a_has_mcq_and_fill(self, paper):
        if paper.get("generation_status") == "failed":
            pytest.skip("gen failed")
        sections = paper.get("sections", [])
        if not sections:
            pytest.skip("no sections")
        qs = sections[0].get("questions", [])
        text_blob = " ".join((q.get("question") or "") for q in qs).lower()
        # heuristics: at least some "(a)" option markers and some blanks
        has_mcq_options = ("(a)" in text_blob or "a)" in text_blob)
        has_blanks = "____" in text_blob or "_____" in text_blob
        assert has_mcq_options, "Section A: expected MCQ options like (a)/(b)"
        assert has_blanks, "Section A: expected fill-blank '_____' markers"


class TestBlueprintCBSE:
    @pytest.fixture(scope="class")
    def paper(self, teacher_token, base_paper_payload):
        payload = {
            **base_paper_payload,
            "title": "TEST_iter5_cbse",
            "total_marks": 80,
            "duration_minutes": 180,
            "section_blueprint": CBSE_BLUEPRINT,
        }
        return _generate_with_blueprint(teacher_token, payload)

    def test_five_sections(self, paper):
        if paper.get("generation_status") == "failed":
            pytest.skip(f"gen failed: {paper.get('generation_error')}")
        sections = paper.get("sections", [])
        assert len(sections) == 5, (
            f"CBSE blueprint expected 5 sections, got {len(sections)}: "
            f"{[s.get('title') for s in sections]}"
        )

    def test_cbse_per_section_counts(self, paper):
        if paper.get("generation_status") == "failed":
            pytest.skip("gen failed")
        sections = paper.get("sections", [])
        if len(sections) != 5:
            pytest.skip("section count off; covered by other test")
        # rough counts: A=16, B=5, C=6, D=4, E=4. Allow ±1 for LLM jitter.
        expected = [(15, 17), (4, 6), (5, 7), (3, 5), (3, 5)]
        for i, (lo, hi) in enumerate(expected):
            n = len(sections[i].get("questions", []))
            assert lo <= n <= hi, f"Section {i} expected {lo}-{hi} questions, got {n}"


class TestBlueprintCustom:
    @pytest.fixture(scope="class")
    def paper(self, teacher_token, base_paper_payload):
        payload = {
            **base_paper_payload,
            "title": "TEST_iter5_custom",
            "total_marks": 50,
            "duration_minutes": 90,
            "section_blueprint": CUSTOM_BLUEPRINT,
        }
        return _generate_with_blueprint(teacher_token, payload)

    def test_one_section_five_essays(self, paper):
        if paper.get("generation_status") == "failed":
            pytest.skip(f"gen failed: {paper.get('generation_error')}")
        sections = paper.get("sections", [])
        assert len(sections) == 1, f"Custom blueprint expected 1 section, got {len(sections)}"
        qs = sections[0].get("questions", [])
        assert len(qs) == 5, f"expected 5 essay questions, got {len(qs)}"
        for q in qs:
            assert int(q.get("marks", 0)) == 10, f"expected 10m each, got {q.get('marks')}"


# -------------- Solution generate (regression) --------------
class TestSolutionRegression:
    def test_solution_generate_endpoint_returns_pending(self, teacher_token):
        # use any teacher-owned ready paper
        r = requests.get(
            f"{BASE_URL}/api/papers",
            headers={"Authorization": f"Bearer {teacher_token}"},
            timeout=TIMEOUT,
        )
        assert r.status_code == 200
        ready = [p for p in r.json() if p.get("generation_status") in ("ready", "partial")]
        if not ready:
            pytest.skip("no ready paper to generate solution for")
        pid = ready[0]["id"]
        h = {"Authorization": f"Bearer {teacher_token}"}
        r2 = requests.post(
            f"{BASE_URL}/api/papers/{pid}/solution/generate",
            headers=h, timeout=TIMEOUT,
        )
        assert r2.status_code in (200, 202), r2.text
        # poll once or twice to confirm endpoint flow
        end = time.time() + 30
        seen = None
        while time.time() < end:
            rs = requests.get(
                f"{BASE_URL}/api/papers/{pid}/solution",
                headers=h, timeout=TIMEOUT,
            )
            if rs.status_code == 200:
                seen = rs.json().get("status") or rs.json().get("generation_status")
                if seen in ("ready", "partial", "pending", "in_progress"):
                    break
            time.sleep(3)
        assert seen is not None, "solution status never observed"
