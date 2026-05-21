"""Tests for locked competitive exam formats and batched generation.

Covers:
- GET /api/competitive-exams/formats
- POST /api/competitive-exams/{id}/generate-paper with JEE_MAINS preset
  (override client-sent question_count/duration_minutes; verify batched
   generation produces ~75 questions)
- GENERIC exam_type respects client-sent values
- /api/papers/{id}/pdf still works after generation
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@bodhi.ai"
ADMIN_PASS = "admin123"
JEE_MAINS_PRESET_ID = "d684ab45-2441-4563-a873-8ee935864b4b"

EXPECTED_FORMATS = {
    "JEE_MAINS": {"question_count": 75, "duration_minutes": 180, "total_marks": 300, "batch_size": 30},
    "JEE_ADV": {"question_count": 54, "duration_minutes": 180, "total_marks": 180, "batch_size": 27},
    "CAT": {"question_count": 66, "duration_minutes": 120, "total_marks": 198, "batch_size": 33},
    "UPSC": {"question_count": 100, "duration_minutes": 120, "total_marks": 200, "batch_size": 34},
    "NEET": {"question_count": 180, "duration_minutes": 200, "total_marks": 720, "batch_size": 30},
}


# ---- Fixtures -------------------------------------------------------------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---- /formats endpoint ----------------------------------------------------
class TestFormatsEndpoint:
    def test_formats_requires_auth(self):
        r = requests.get(f"{API}/competitive-exams/formats", timeout=15)
        # Auth-protected per spec
        assert r.status_code in (401, 403), f"expected 401/403 unauth, got {r.status_code}"

    def test_formats_returns_all_five(self, auth_headers):
        r = requests.get(f"{API}/competitive-exams/formats", headers=auth_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, dict)
        for code, expected in EXPECTED_FORMATS.items():
            assert code in data, f"missing {code} in /formats response"
            entry = data[code]
            for field in ("label", "question_count", "duration_minutes", "total_marks",
                          "format_distribution", "batch_size", "subjects", "notes"):
                assert field in entry, f"{code} missing field {field}"
            assert entry["question_count"] == expected["question_count"]
            assert entry["duration_minutes"] == expected["duration_minutes"]
            assert entry["total_marks"] == expected["total_marks"]
            assert entry["batch_size"] == expected["batch_size"]
            assert isinstance(entry["subjects"], list) and len(entry["subjects"]) > 0
            assert isinstance(entry["format_distribution"], dict)


# ---- Locked override on generate-paper -----------------------------------
def _poll_paper(paper_id: str, headers: dict, timeout_s: int = 240) -> dict:
    """Poll /api/papers/{id} until generation_status != pending or timeout."""
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = requests.get(f"{API}/papers/{paper_id}", headers=headers, timeout=30)
        if r.status_code == 200:
            last = r.json()
            if last.get("generation_status") in ("ready", "failed"):
                return last
        time.sleep(5)
    return last or {}


class TestLockedFormatOverride:
    def test_jee_mains_overrides_client_values(self, auth_headers):
        """Send absurd client values (5q/10min) — backend must persist 75/180/300."""
        payload = {
            "exam_id": JEE_MAINS_PRESET_ID,
            "title": "TEST_locked_jee_mains",
            "topics": ["Physics", "Mathematics"],
            "difficulty": "medium",
            "question_count": 5,
            "duration_minutes": 10,
            "format_distribution": {"mcq": 100},
            "custom_instructions": "",
        }
        r = requests.post(
            f"{API}/competitive-exams/{JEE_MAINS_PRESET_ID}/generate-paper",
            json=payload, headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200, f"generate POST failed: {r.status_code} {r.text}"
        paper = r.json()
        paper_id = paper["id"]
        # Immediate persistence checks (paper_doc creation)
        assert paper["duration_minutes"] == 180, f"expected duration locked to 180, got {paper['duration_minutes']}"
        assert paper["total_marks"] == 300, f"expected total_marks locked to 300, got {paper['total_marks']}"
        assert paper["format_distribution"] == {"mcq": 80, "numerical": 20}, paper["format_distribution"]

        # Poll for background generation to finalise
        final = _poll_paper(paper_id, auth_headers, timeout_s=240)
        assert final.get("generation_status") == "ready", (
            f"generation did not reach ready in 240s: status={final.get('generation_status')} "
            f"err={final.get('generation_error')}"
        )
        # Validate locked fields persist
        assert final["duration_minutes"] == 180
        assert final["total_marks"] == 300
        assert final["format_distribution"] == {"mcq": 80, "numerical": 20}
        assert final.get("exam_type") == "JEE_MAINS"

        # Question count: aim is 75, accept >= 60 per main agent variance allowance
        sections = final.get("sections") or []
        q_count = sum(len(s.get("questions") or []) for s in sections)
        assert q_count >= 60, f"expected ~75 questions (>=60 acceptable), got {q_count}"
        # And not absurdly over the lock (we truncate to total_q=75)
        assert q_count <= 75, f"expected <=75 (truncated to spec), got {q_count}"

        # Save id for PDF test
        TestLockedFormatOverride._jee_paper_id = paper_id

    def test_pdf_download_for_jee_paper(self, auth_headers):
        paper_id = getattr(TestLockedFormatOverride, "_jee_paper_id", None)
        if not paper_id:
            pytest.skip("no jee paper id from previous test")
        r = requests.get(f"{API}/papers/{paper_id}/pdf", headers=auth_headers, timeout=60)
        assert r.status_code == 200, f"pdf failed: {r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert len(r.content) > 1024, "pdf suspiciously small"


# ---- GENERIC exam respects client values ---------------------------------
class TestGenericRespectsClient:
    def test_generic_exam_uses_client_values(self, auth_headers):
        # Create a GENERIC exam
        exam_payload = {
            "name": f"TEST_generic_{uuid.uuid4().hex[:6]}",
            "description": "test generic",
            "is_shared": True,
            "exam_type": "GENERIC",
        }
        r = requests.post(f"{API}/competitive-exams", json=exam_payload, headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text
        exam_id = r.json()["id"]

        # Generate with small custom counts
        payload = {
            "exam_id": exam_id,
            "title": "TEST_generic_paper",
            "topics": ["Algebra"],
            "difficulty": "medium",
            "question_count": 5,
            "duration_minutes": 25,
            "format_distribution": {"mcq": 100},
            "custom_instructions": "",
        }
        r = requests.post(
            f"{API}/competitive-exams/{exam_id}/generate-paper",
            json=payload, headers=auth_headers, timeout=30,
        )
        assert r.status_code == 200, r.text
        paper = r.json()
        # GENERIC must respect client-sent values
        assert paper["duration_minutes"] == 25, f"GENERIC should respect 25, got {paper['duration_minutes']}"
        assert paper["total_marks"] == 5, f"GENERIC default 1mark/q -> 5, got {paper['total_marks']}"
        assert paper["format_distribution"] == {"mcq": 100}
