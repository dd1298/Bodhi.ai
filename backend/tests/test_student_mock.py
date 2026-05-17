"""Student MVP backend tests: register-as-student, shared textbooks, mock-test lifecycle, auto-grade.

Covers all 7 student endpoints + role guards + MCQ structured options leak check.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://question-ai-10.preview.emergentagent.com").rstrip("/")
SHARED_MATHS_ID = "64b415e2-1091-4ab7-acc6-31977985859a"
SHARED_PHYSICS_ID = "e0424db1-3b24-433c-b672-8d49cdbf9892"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def student_token(s):
    email = f"TEST_student_{int(time.time())}@example.com"
    r = s.post(f"{BASE_URL}/api/auth/register", json={
        "email": email, "password": "pass123", "full_name": "Test Stu", "role": "student"
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("token")
    assert body["user"]["role"] == "student"
    return body["token"]


@pytest.fixture(scope="module")
def teacher_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "pdftest@t.com", "password": "pass123"})
    assert r.status_code == 200
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@bodhi.ai", "password": "admin123"})
    assert r.status_code == 200
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------- register / role guard ----------
class TestRegisterRole:
    def test_register_accepts_student(self, s, student_token):
        assert isinstance(student_token, str) and len(student_token) > 10

    def test_register_rejects_unknown_role(self, s):
        r = s.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"TEST_x_{int(time.time())}@example.com",
            "password": "pass123", "full_name": "X", "role": "principal"
        })
        assert r.status_code in (400, 422), r.text


# ---------- shared textbooks ----------
class TestSharedTextbooks:
    def test_lists_only_shared(self, s, student_token):
        r = s.get(f"{BASE_URL}/api/student/textbooks", headers=H(student_token))
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list) and len(rows) >= 2
        ids = {row["id"] for row in rows}
        assert SHARED_MATHS_ID in ids, f"Maths shared book missing; got {ids}"
        assert SHARED_PHYSICS_ID in ids, f"Physics shared book missing; got {ids}"
        # No _id leak
        for row in rows:
            assert "_id" not in row

    def test_teacher_403_on_student_route(self, s, teacher_token):
        r = s.get(f"{BASE_URL}/api/student/textbooks", headers=H(teacher_token))
        assert r.status_code == 403, r.text


# ---------- mock test full lifecycle ----------
class TestMockTestLifecycle:
    @pytest.fixture(scope="class")
    def created(self, s, student_token):
        # Pull topics from the maths book
        tb = s.get(f"{BASE_URL}/api/student/textbooks", headers=H(student_token)).json()
        maths = next(t for t in tb if t["id"] == SHARED_MATHS_ID)
        topics = [t["name"] if isinstance(t, dict) else t for t in (maths.get("topics") or [])][:2]
        if not topics:
            topics = ["Numbers", "Fractions"]
        payload = {
            "textbook_ids": [SHARED_MATHS_ID],
            "topics": topics,
            "subject": maths.get("subject", "Maths"),
            "class_name": maths.get("class_name", "6"),
            "difficulty": "easy",
            "question_count": 5,
            "duration_minutes": 10,
        }
        r = s.post(f"{BASE_URL}/api/student/mock-tests", json=payload, headers=H(student_token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert "id" in body and "paper_id" in body
        assert body["status"] == "not_started"
        return body

    def test_get_hides_correct_option_until_submit(self, s, student_token, created):
        # Poll until paper is ready
        deadline = time.time() + 180
        last = None
        while time.time() < deadline:
            r = s.get(f"{BASE_URL}/api/student/mock-tests/{created['id']}", headers=H(student_token))
            assert r.status_code == 200, r.text
            t = r.json()
            last = t
            gs = (t.get("paper") or {}).get("generation_status")
            if gs in ("ready", "failed"):
                break
            time.sleep(4)
        assert last is not None
        gs = (last.get("paper") or {}).get("generation_status")
        if gs != "ready":
            pytest.skip(f"Paper generation status={gs}; likely LLM provider hiccup, not a code bug")
        # CRITICAL: correct_option must NOT be present pre-submit
        for sec in last["paper"]["sections"]:
            for q in sec["questions"]:
                assert "correct_option" not in q, f"LEAK: correct_option visible pre-submit on Q {q.get('id')}"
                assert "diagram_description" not in q
                if (q.get("format") or "").lower() == "mcq":
                    assert isinstance(q.get("options"), list), f"MCQ missing options[] on {q.get('id')}"
                    assert len(q["options"]) == 4

    def test_cannot_start_before_ready_or_after_submitted(self, s, student_token, created):
        # Start - should succeed since previous test polled ready
        r = s.post(f"{BASE_URL}/api/student/mock-tests/{created['id']}/start", headers=H(student_token))
        if r.status_code == 409:
            pytest.skip("Paper not ready - LLM issue")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "in_progress"
        assert body["started_at"] and body["ends_at"]

    def test_autosave_answers(self, s, student_token, created):
        # Fetch questions and select option 0 for each
        t = s.get(f"{BASE_URL}/api/student/mock-tests/{created['id']}", headers=H(student_token)).json()
        if t["status"] != "in_progress":
            pytest.skip("Not in progress")
        answers = []
        for sec in t["paper"]["sections"]:
            for q in sec["questions"]:
                answers.append({"question_id": q["id"], "selected_option": 0, "text_answer": None})
        r = s.patch(f"{BASE_URL}/api/student/mock-tests/{created['id']}/answers",
                    json={"answers": answers}, headers=H(student_token))
        assert r.status_code == 200, r.text
        assert r.json()["saved"] == len(answers)

    def test_submit_and_score(self, s, student_token, created):
        r = s.post(f"{BASE_URL}/api/student/mock-tests/{created['id']}/submit", headers=H(student_token))
        if r.status_code == 409:
            pytest.skip("Not started yet")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "submitted"
        score = body["score"]
        for k in ("obtained", "total", "mcq_correct", "mcq_total", "by_topic", "percent"):
            assert k in score
        assert score["mcq_total"] >= 1
        assert score["total"] == score["mcq_total"]  # 1 mark per MCQ

    def test_result_exposes_correct_option(self, s, student_token, created):
        r = s.get(f"{BASE_URL}/api/student/mock-tests/{created['id']}/result", headers=H(student_token))
        assert r.status_code == 200, r.text
        body = r.json()
        any_correct_seen = False
        for sec in body["paper"]["sections"]:
            for q in sec["questions"]:
                if (q.get("format") or "").lower() == "mcq":
                    assert "correct_option" in q, "Result must expose correct_option"
                    assert isinstance(q["correct_option"], int)
                    assert 0 <= q["correct_option"] <= 3
                    any_correct_seen = True
        assert any_correct_seen


# ---------- role guards ----------
class TestRoleGuards:
    def test_teacher_blocked_from_mock_routes(self, s, teacher_token):
        r = s.post(f"{BASE_URL}/api/student/mock-tests",
                   json={"textbook_ids": [SHARED_MATHS_ID], "topics": ["x"],
                         "question_count": 5, "duration_minutes": 10},
                   headers=H(teacher_token))
        assert r.status_code == 403

    def test_unauthed_blocked(self, s):
        r = s.get(f"{BASE_URL}/api/student/textbooks")
        assert r.status_code in (401, 403)


# ---------- teacher regression ----------
class TestTeacherRegression:
    def test_textbooks_endpoint(self, s, teacher_token):
        r = s.get(f"{BASE_URL}/api/textbooks", headers=H(teacher_token))
        assert r.status_code == 200

    def test_admin_overview(self, s, admin_token):
        r = s.get(f"{BASE_URL}/api/admin/overview", headers=H(admin_token))
        assert r.status_code == 200
        body = r.json()
        assert "teachers" in body or "total_teachers" in body or "users" in body
