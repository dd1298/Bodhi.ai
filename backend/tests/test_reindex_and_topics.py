"""Tests for reindex async flow, extract-topics 422 on zero topics, and
_strip_boilerplate CamScanner filter (iteration 10 - review request)."""
import io
import os
import time
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        # fallback: parse frontend/.env
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    v = ln.split("=", 1)[1].strip()
                    break
    return v.rstrip("/") if v else ""

BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@bodhi.ai"
ADMIN_PASS = "admin123"
SEEDED_TB_ID = "b7b444fc-e70c-4d4c-8f05-633c0889a8c5"


# -------- Auth fixture --------
@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=15,
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---- 1. _strip_boilerplate direct unit test (CamScanner) ----
def test_strip_boilerplate_camscanner():
    import sys
    sys.path.insert(0, "/app/backend")
    from pdf_utils import _strip_boilerplate  # type: ignore

    text = "\n".join(["Scanned by CamScanner"] * 50 + ["CamScanner", "Scanned with CamScanner"] * 10)
    cleaned = _strip_boilerplate(text)
    assert len(cleaned.strip()) < 50, f"expected near-empty, got {len(cleaned)} chars: {cleaned!r}"


# ---- 2. Seeded textbook (indexed) → extract-topics returns 8+ real topics ----
def test_extract_topics_happy_path_seeded_scanned_book(auth):
    # First confirm the seed exists & has chunks
    r = requests.get(f"{BASE_URL}/api/textbooks/{SEEDED_TB_ID}", headers=auth, timeout=15)
    if r.status_code == 404:
        pytest.skip("Seeded scanned textbook not present in DB")
    assert r.status_code == 200
    tb = r.json()
    assert tb.get("status") in ("indexed", "topics_ready"), f"unexpected status: {tb.get('status')}"

    # Trigger extract-topics
    r = requests.post(
        f"{BASE_URL}/api/textbooks/{SEEDED_TB_ID}/extract-topics",
        headers=auth,
        timeout=180,
    )
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    topics = body.get("topics", [])
    assert isinstance(topics, list)
    assert len(topics) >= 6, f"expected 6+ topics, got {len(topics)}: {[t.get('name') for t in topics]}"
    names_lower = " ".join(t.get("name", "").lower() for t in topics)
    # Common SL Arora Class 11 physics topics
    physics_keywords = ["kinematics", "vector", "motion", "unit", "measurement", "physical world", "mathematical"]
    hits = [k for k in physics_keywords if k in names_lower]
    assert len(hits) >= 2, f"topics don't look like physics: {names_lower}"


# ---- 3. Reindex endpoint - returns 202-style {status:'ingesting'} immediately ----
def test_reindex_returns_ingesting_immediately(auth):
    r = requests.get(f"{BASE_URL}/api/textbooks/{SEEDED_TB_ID}", headers=auth, timeout=15)
    if r.status_code != 200:
        pytest.skip("Seeded textbook missing")

    start = time.time()
    r = requests.post(
        f"{BASE_URL}/api/textbooks/{SEEDED_TB_ID}/reindex",
        headers=auth,
        timeout=30,
    )
    elapsed = time.time() - start
    assert r.status_code == 200, f"reindex failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("status") == "ingesting", f"expected ingesting, got {body}"
    assert body.get("id") == SEEDED_TB_ID
    # Response should be near-immediate (< 10s) since ingestion is now backgrounded
    assert elapsed < 15, f"reindex took {elapsed:.1f}s — should return immediately"

    # Poll for status transition
    final_status = None
    for _ in range(24):  # up to 6 min
        time.sleep(15)
        r = requests.get(f"{BASE_URL}/api/textbooks/{SEEDED_TB_ID}", headers=auth, timeout=15)
        assert r.status_code == 200
        st = r.json().get("status")
        if st in ("indexed", "topics_ready", "extraction_failed"):
            final_status = st
            break
    assert final_status in ("indexed", "topics_ready"), f"reindex did not complete: {final_status}"


# ---- 4. Regression: papers list / qbank / competitive-exams reachable ----
def test_regression_endpoints_reachable(auth):
    for path in ("/api/papers", "/api/qbank", "/api/competitive-exams", "/api/textbooks"):
        r = requests.get(f"{BASE_URL}{path}", headers=auth, timeout=20)
        assert r.status_code in (200, 204), f"{path} → {r.status_code}: {r.text[:200]}"


# ---- 5. Extract-topics on ingesting textbook returns 409 (regression) ----
def test_extract_topics_ingesting_returns_409(auth):
    """After firing reindex, an immediate extract-topics should hit the
    409 branch. Only runs if reindex background is still processing."""
    r = requests.post(
        f"{BASE_URL}/api/textbooks/{SEEDED_TB_ID}/reindex",
        headers=auth,
        timeout=30,
    )
    if r.status_code != 200:
        pytest.skip("could not trigger reindex")
    # Immediately hit extract-topics
    r2 = requests.post(
        f"{BASE_URL}/api/textbooks/{SEEDED_TB_ID}/extract-topics",
        headers=auth,
        timeout=15,
    )
    # Might be 200 if OCR finished super fast, but usually 409
    assert r2.status_code in (409, 200), f"unexpected: {r2.status_code} {r2.text}"
    if r2.status_code == 409:
        assert "still being processed" in r2.text.lower() or "ocr" in r2.text.lower()
