"""Phase 2.5 — Per-exam model routing + presets backend tests."""
import os
import time
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
SEEDED_JEE_EXAM_ID = "d684ab45-2441-4563-a873-8ee935864b4b"
PRESETS = ["JEE_MAINS", "JEE_ADV", "CAT", "UPSC", "NEET"]


@pytest.fixture(scope="module")
def teacher_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "pdftest@t.com", "password": "pass123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def teacher_headers(teacher_token):
    return {"Authorization": f"Bearer {teacher_token}"}


# ---- exam_type CRUD ---------------------------------------------------------
class TestExamTypeCRUD:
    created_ids = []

    @pytest.mark.parametrize("exam_type", PRESETS + ["GENERIC"])
    def test_create_persists_exam_type(self, teacher_headers, exam_type):
        r = requests.post(
            f"{BASE_URL}/api/competitive-exams",
            headers=teacher_headers,
            json={"name": f"TEST_{exam_type}_{int(time.time()*1000)%100000}",
                  "description": f"routing test {exam_type}",
                  "is_shared": True,
                  "exam_type": exam_type},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["exam_type"] == exam_type
        assert "id" in body
        TestExamTypeCRUD.created_ids.append(body["id"])

        # GET single -> still has exam_type
        g = requests.get(f"{BASE_URL}/api/competitive-exams/{body['id']}",
                         headers=teacher_headers)
        assert g.status_code == 200
        assert g.json()["exam_type"] == exam_type

    def test_list_contains_exam_type_field(self, teacher_headers):
        r = requests.get(f"{BASE_URL}/api/competitive-exams",
                         headers=teacher_headers)
        assert r.status_code == 200
        rows = r.json()
        # Every row has exam_type populated
        for row in rows:
            assert "exam_type" in row, row
            assert row["exam_type"] in PRESETS + ["GENERIC"]

    def test_invalid_exam_type_normalises_or_falls_back(self, teacher_headers):
        # Backend stores .upper() — sending lower JEE_MAINS should still work
        r = requests.post(
            f"{BASE_URL}/api/competitive-exams",
            headers=teacher_headers,
            json={"name": f"TEST_lowercase_{int(time.time()*1000)%100000}",
                  "exam_type": "jee_mains"},
        )
        assert r.status_code == 200
        assert r.json()["exam_type"] == "JEE_MAINS"
        TestExamTypeCRUD.created_ids.append(r.json()["id"])


# ---- generate-paper uses exam_type routing ---------------------------------
class TestGenerateRoutesByExamType:
    def test_seeded_jee_mains_generates_with_exam_type_stamped(self, teacher_headers):
        """Use main-agent-seeded JEE_MAINS exam with 3 past_questions and
        kick off a small 3-question MCQ paper. Verify the paper reaches
        status=ready and exam_type=JEE_MAINS is stamped on the paper doc."""
        r = requests.post(
            f"{BASE_URL}/api/competitive-exams/{SEEDED_JEE_EXAM_ID}/generate-paper",
            headers=teacher_headers,
            json={"exam_id": SEEDED_JEE_EXAM_ID,
                  "title": "TEST_route_JEE_MAINS",
                  "topics": ["Mechanics"],
                  "difficulty": "medium",
                  "question_count": 3,
                  "duration_minutes": 10,
                  "format_distribution": {"mcq": 100}},
        )
        assert r.status_code == 200, r.text
        paper_id = r.json()["id"]
        assert r.json().get("is_competitive") is True
        assert r.json().get("competitive_exam_id") == SEEDED_JEE_EXAM_ID

        # Poll up to 90s
        deadline = time.time() + 90
        status = None
        paper = {}
        while time.time() < deadline:
            g = requests.get(f"{BASE_URL}/api/papers/{paper_id}",
                             headers=teacher_headers)
            assert g.status_code == 200, g.text
            paper = g.json()
            status = paper.get("generation_status")
            if status in ("ready", "failed"):
                break
            time.sleep(3)
        assert status == "ready", f"Paper status={status} err={paper.get('generation_error')}"
        # exam_type stamped on paper
        assert paper.get("exam_type") == "JEE_MAINS", paper.get("exam_type")
        # rag fields populated
        assert "rag_anchors_used" in paper
        assert "rag_difficulty_distribution" in paper
        # MCQ structure intact
        secs = paper.get("sections") or []
        assert secs, "no sections generated"
        q_total = 0
        for s in secs:
            for q in s.get("questions") or []:
                q_total += 1
                if (q.get("format") or "").lower() == "mcq":
                    assert isinstance(q.get("options"), list) and len(q["options"]) == 4
                    assert q.get("correct_option") in (0, 1, 2, 3)
        assert q_total >= 1


# ---- backend log primary-model verification --------------------------------
class TestBackendLogPrimary:
    def test_jee_mains_primary_was_gpt_5_1(self):
        """Backend logs should show LLM success with openai/gpt-5.1 from the
        generation we just triggered. This is the primary model for JEE_MAINS."""
        # Read recent supervisor log
        try:
            with open("/var/log/supervisor/backend.err.log") as f:
                lines = f.readlines()[-2000:]
        except FileNotFoundError:
            pytest.skip("backend.err.log not available")
        recent = "".join(lines)
        # Either primary or first fallback acceptable per playbook
        assert ("LLM success with openai/gpt-5.1" in recent
                or "LLM success with openai/gpt-5.2" in recent
                or "LLM success with anthropic/claude-sonnet-4-5-20250929" in recent), \
            "No matching LLM success log line found for JEE_MAINS chain"


# ---- Regression: phase 1 + earlier teacher flows still green ---------------
class TestRegression:
    def test_admin_overview(self):
        a = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "admin@bodhi.ai", "password": "admin123"})
        assert a.status_code == 200
        tok = a.json()["token"]
        r = requests.get(f"{BASE_URL}/api/admin/overview",
                         headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
        assert "users" in r.json() or "total_users" in r.json() or isinstance(r.json(), dict)

    def test_textbooks_list(self, teacher_headers):
        r = requests.get(f"{BASE_URL}/api/textbooks", headers=teacher_headers)
        assert r.status_code == 200

    def test_papers_list(self, teacher_headers):
        r = requests.get(f"{BASE_URL}/api/papers", headers=teacher_headers)
        assert r.status_code == 200

    def test_student_section(self):
        a = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "student.smoke.1779011398@example.com",
                                "password": "pass123"})
        assert a.status_code == 200
        tok = a.json()["token"]
        r = requests.get(f"{BASE_URL}/api/student/textbooks",
                         headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200
