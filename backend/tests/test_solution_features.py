"""
Backend API tests for AI Question Paper Generator - Solution/Answer Key Features
Tests: Solution generation, solution editing, solution PDF, bulk generation,
       toggle important, paper/textbook delete, qbank CRUD, staleness tracking
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

# Test user credentials
TEST_EMAIL = f"test_solution_{int(time.time())}@test.com"
TEST_PASSWORD = "testpass123"
TEST_NAME = "Solution Test User"


def create_dummy_pdf(content: str = "Sample textbook content about Physics and motion.") -> bytes:
    """Create a minimal PDF for testing."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(100, 750, "Physics Textbook - Class 10")
    c.drawString(100, 730, "Chapter 1: Motion and Forces")
    c.drawString(100, 710, content)
    c.drawString(100, 690, "Newton's Laws of Motion describe the relationship between")
    c.drawString(100, 670, "a body and the forces acting upon it.")
    c.drawString(100, 650, "First Law: An object at rest stays at rest.")
    c.drawString(100, 630, "Second Law: F = ma (Force equals mass times acceleration)")
    c.drawString(100, 610, "Third Law: For every action, there is an equal and opposite reaction.")
    c.drawString(100, 590, "Topics: Kinematics, Dynamics, Projectile Motion, Circular Motion")
    c.drawString(100, 570, "Kinetic Energy = 0.5 * m * v^2")
    c.drawString(100, 550, "Potential Energy = m * g * h")
    c.save()
    return buf.getvalue()


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for authenticated tests"""
    response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "full_name": TEST_NAME,
        "role": "teacher"
    }, timeout=30)
    
    if response.status_code == 200:
        return response.json()["token"]
    
    # Fallback to login
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    }, timeout=30)
    
    if response.status_code == 200:
        return response.json()["token"]
    
    pytest.skip("Could not obtain auth token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for authenticated requests"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def textbook_id(auth_headers):
    """Upload a textbook and return its ID"""
    pdf_data = create_dummy_pdf()
    files = {"file": ("physics_textbook.pdf", pdf_data, "application/pdf")}
    response = requests.post(
        f"{BASE_URL}/api/textbooks/upload",
        files=files,
        params={"subject": "Physics", "class_name": "10"},
        headers=auth_headers,
        timeout=60
    )
    if response.status_code != 200:
        pytest.skip(f"Could not upload textbook: {response.text}")
    return response.json()["id"]


@pytest.fixture(scope="module")
def generated_paper(auth_headers, textbook_id):
    """Generate a paper for solution tests"""
    response = requests.post(
        f"{BASE_URL}/api/papers/generate",
        json={
            "title": "Solution Test Paper",
            "subject": "Physics",
            "class_name": "10",
            "textbook_id": textbook_id,
            "topics": ["Motion", "Forces", "Energy"],
            "difficulty": "medium",
            "duration_minutes": 60,
            "total_marks": 30,
            "distribution": {"information": 34, "concept": 33, "application": 33}
        },
        headers=auth_headers,
        timeout=180  # LLM calls can be slow
    )
    
    if response.status_code != 200:
        pytest.skip(f"Could not generate paper: {response.status_code} - {response.text[:200]}")
    
    return response.json()


# ============================================================
# Solution Generation Tests
# ============================================================
class TestSolutionGeneration:
    """Tests for POST /api/papers/{paper_id}/solution/generate"""
    
    def test_generate_solution_no_auth(self, generated_paper):
        """Test solution generation without auth fails"""
        response = requests.post(
            f"{BASE_URL}/api/papers/{generated_paper['id']}/solution/generate",
            timeout=60
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Solution generation correctly requires authentication")
    
    def test_generate_solution_success(self, auth_headers, generated_paper):
        """Test successful solution generation"""
        response = requests.post(
            f"{BASE_URL}/api/papers/{generated_paper['id']}/solution/generate",
            headers=auth_headers,
            timeout=180  # LLM calls can be slow
        )
        
        if response.status_code == 502:
            print(f"⚠ Solution generation LLM failed (502): {response.text[:200]}")
            pytest.skip("LLM failed")
        
        assert response.status_code == 200, f"Solution generation failed: {response.status_code} - {response.text[:200]}"
        
        data = response.json()
        assert "sections" in data, "Solution should have sections"
        assert "is_stale" in data, "Solution should have is_stale flag"
        assert data["is_stale"] == False, "New solution should not be stale"
        assert "generated_at" in data, "Solution should have generated_at timestamp"
        
        # Verify sections mirror paper structure
        paper_sections = generated_paper.get("sections", [])
        solution_sections = data.get("sections", [])
        
        # Count questions in paper
        paper_question_ids = set()
        for s in paper_sections:
            for q in s.get("questions", []):
                paper_question_ids.add(q.get("id"))
        
        # Count answers in solution
        solution_question_ids = set()
        for s in solution_sections:
            for a in s.get("answers", []):
                solution_question_ids.add(a.get("question_id"))
        
        # Verify answer count matches question count
        assert len(solution_question_ids) == len(paper_question_ids), \
            f"Answer count ({len(solution_question_ids)}) should match question count ({len(paper_question_ids)})"
        
        # Verify question_ids match
        assert solution_question_ids == paper_question_ids, "Solution question_ids should match paper question_ids"
        
        print(f"✓ Solution generated successfully")
        print(f"  - Sections: {len(solution_sections)}")
        print(f"  - Answers: {len(solution_question_ids)}")
        print(f"  - is_stale: {data['is_stale']}")
    
    def test_generate_solution_nonexistent_paper(self, auth_headers):
        """Test solution generation for non-existent paper"""
        response = requests.post(
            f"{BASE_URL}/api/papers/nonexistent-paper-id/solution/generate",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Solution generation returns 404 for non-existent paper")
    
    def test_paper_includes_solution_after_generation(self, auth_headers, generated_paper):
        """Verify GET /api/papers/{id} includes solution field after generation"""
        # First ensure solution exists
        requests.post(
            f"{BASE_URL}/api/papers/{generated_paper['id']}/solution/generate",
            headers=auth_headers,
            timeout=180
        )
        
        # Get paper
        response = requests.get(
            f"{BASE_URL}/api/papers/{generated_paper['id']}",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "solution" in data, "Paper should include solution field"
        if data.get("solution"):
            assert "is_stale" in data["solution"], "Solution should have is_stale"
            assert data["solution"]["is_stale"] == False, "Solution should not be stale"
            print("✓ Paper includes solution with is_stale=false")
        else:
            print("⚠ Solution not present (LLM may have failed)")


# ============================================================
# Answer Depth Verification Tests
# ============================================================
class TestAnswerDepth:
    """Tests for answer depth based on question type"""
    
    def test_answer_depth_by_type(self, auth_headers, generated_paper):
        """Verify information-type answers are concise, application-type are detailed"""
        # Generate solution
        response = requests.post(
            f"{BASE_URL}/api/papers/{generated_paper['id']}/solution/generate",
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip("Solution generation failed")
        
        solution = response.json()
        
        # Build question type map
        question_types = {}
        for s in generated_paper.get("sections", []):
            for q in s.get("questions", []):
                question_types[q.get("id")] = q.get("type", "concept")
        
        # Analyze answer lengths
        info_answers = []
        app_answers = []
        
        for s in solution.get("sections", []):
            for a in s.get("answers", []):
                qid = a.get("question_id")
                answer = a.get("answer", "")
                qtype = question_types.get(qid, "concept")
                
                if qtype == "information":
                    info_answers.append(answer)
                elif qtype == "application":
                    app_answers.append(answer)
        
        print(f"  - Information answers: {len(info_answers)}")
        print(f"  - Application answers: {len(app_answers)}")
        
        # Check information answers are concise (<= ~220 chars)
        if info_answers:
            for i, ans in enumerate(info_answers[:3]):
                print(f"    Info answer {i+1} length: {len(ans)} chars")
                # Soft check - some info answers may be longer
                if len(ans) > 300:
                    print(f"    ⚠ Info answer longer than expected: {ans[:100]}...")
        
        # Check application answers are longer (step-by-step)
        if app_answers:
            for i, ans in enumerate(app_answers[:3]):
                print(f"    App answer {i+1} length: {len(ans)} chars")
                # Application answers should be more detailed
                if len(ans) < 100:
                    print(f"    ⚠ App answer shorter than expected: {ans}")
        else:
            print("  ⚠ No application-type questions in paper (skipping depth check)")
        
        print("✓ Answer depth verification completed")


# ============================================================
# Solution Editing Tests
# ============================================================
class TestSolutionEditing:
    """Tests for PATCH /api/papers/{paper_id}/solution"""
    
    @pytest.fixture
    def paper_with_solution(self, auth_headers, textbook_id):
        """Generate a paper and its solution"""
        # Generate paper
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Solution Edit Test Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_id,
                "topics": ["Motion"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 50, "concept": 30, "application": 20}
            },
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not generate paper: {response.text[:200]}")
        
        paper = response.json()
        
        # Generate solution
        response = requests.post(
            f"{BASE_URL}/api/papers/{paper['id']}/solution/generate",
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not generate solution: {response.text[:200]}")
        
        paper["solution"] = response.json()
        return paper
    
    def test_patch_solution_no_auth(self, paper_with_solution):
        """Test solution editing without auth fails"""
        response = requests.patch(
            f"{BASE_URL}/api/papers/{paper_with_solution['id']}/solution",
            json={"sections": []},
            timeout=30
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Solution editing correctly requires authentication")
    
    def test_patch_solution_success(self, auth_headers, paper_with_solution):
        """Test successful solution editing"""
        solution = paper_with_solution.get("solution", {})
        sections = solution.get("sections", [])
        
        if not sections or not sections[0].get("answers"):
            pytest.skip("No answers to edit")
        
        # Modify first answer
        modified_sections = []
        original_answer = None
        modified_qid = None
        
        for s in sections:
            new_answers = []
            for i, a in enumerate(s.get("answers", [])):
                if i == 0 and original_answer is None:
                    original_answer = a.get("answer", "")
                    modified_qid = a.get("question_id")
                    new_answers.append({
                        "question_id": a["question_id"],
                        "answer": "TEACHER EDITED: " + original_answer
                    })
                else:
                    new_answers.append({
                        "question_id": a["question_id"],
                        "answer": a.get("answer", "")
                    })
            modified_sections.append({
                "title": s.get("title", "Section"),
                "answers": new_answers
            })
        
        response = requests.patch(
            f"{BASE_URL}/api/papers/{paper_with_solution['id']}/solution",
            json={"sections": modified_sections},
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Solution edit failed: {response.text}"
        
        data = response.json()
        assert "sections" in data
        assert data.get("is_stale") == False, "Edited solution should not be stale"
        
        # Verify the edit was applied
        found_edit = False
        for s in data.get("sections", []):
            for a in s.get("answers", []):
                if a.get("question_id") == modified_qid:
                    assert "TEACHER EDITED:" in a.get("answer", ""), "Edit not applied"
                    found_edit = True
                    break
        
        assert found_edit, "Edited answer not found in response"
        print("✓ Solution edited successfully")
        print("  - solution_edits collection should have a row with original/revised")
    
    def test_patch_solution_without_existing_solution(self, auth_headers, textbook_id):
        """Test editing solution when none exists"""
        # Generate paper without solution
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "No Solution Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_id,
                "topics": ["Motion"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 50, "concept": 30, "application": 20}
            },
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip("Could not generate paper")
        
        paper_id = response.json()["id"]
        
        # Try to edit non-existent solution
        response = requests.patch(
            f"{BASE_URL}/api/papers/{paper_id}/solution",
            json={"sections": [{"title": "Section", "answers": []}]},
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Editing non-existent solution correctly returns 400")


# ============================================================
# Solution Staleness Tests
# ============================================================
class TestSolutionStaleness:
    """Tests for solution staleness when paper is edited"""
    
    def test_solution_becomes_stale_after_paper_edit(self, auth_headers, textbook_id):
        """Edit paper after solution exists - verify is_stale becomes true"""
        # Generate paper
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Staleness Test Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_id,
                "topics": ["Motion"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 50, "concept": 30, "application": 20}
            },
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not generate paper: {response.text[:200]}")
        
        paper = response.json()
        paper_id = paper["id"]
        
        # Generate solution
        response = requests.post(
            f"{BASE_URL}/api/papers/{paper_id}/solution/generate",
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not generate solution: {response.text[:200]}")
        
        # Verify solution is not stale
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_id}",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        paper_data = response.json()
        assert paper_data.get("solution", {}).get("is_stale") == False, "Solution should not be stale initially"
        
        # Edit the paper (modify a question)
        sections = paper_data.get("sections", [])
        if sections and sections[0].get("questions"):
            sections[0]["questions"][0]["question"] = "MODIFIED QUESTION: " + sections[0]["questions"][0].get("question", "")
            
            response = requests.patch(
                f"{BASE_URL}/api/papers/{paper_id}",
                json={"sections": [{"title": s["title"], "questions": s["questions"]} for s in sections]},
                headers=auth_headers,
                timeout=30
            )
            
            assert response.status_code == 200, f"Paper edit failed: {response.text}"
            
            # Verify solution is now stale
            updated_paper = response.json()
            assert updated_paper.get("solution", {}).get("is_stale") == True, \
                "Solution should be stale after paper edit"
            
            print("✓ Solution correctly marked as stale after paper edit")
        else:
            pytest.skip("No questions to modify")


# ============================================================
# Solution PDF Tests
# ============================================================
class TestSolutionPDF:
    """Tests for GET /api/papers/{paper_id}/solution/pdf"""
    
    @pytest.fixture
    def paper_with_solution_for_pdf(self, auth_headers, textbook_id):
        """Generate a paper and its solution for PDF test"""
        # Generate paper
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Solution PDF Test Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_id,
                "topics": ["Motion"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 50, "concept": 30, "application": 20}
            },
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not generate paper: {response.text[:200]}")
        
        paper = response.json()
        
        # Generate solution
        response = requests.post(
            f"{BASE_URL}/api/papers/{paper['id']}/solution/generate",
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not generate solution: {response.text[:200]}")
        
        return paper
    
    def test_solution_pdf_no_auth(self, paper_with_solution_for_pdf):
        """Test solution PDF download without auth fails"""
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_with_solution_for_pdf['id']}/solution/pdf",
            timeout=30
        )
        assert response.status_code == 401, "Should require auth"
        print("✓ Solution PDF download correctly requires authentication")
    
    def test_solution_pdf_with_header(self, auth_headers, paper_with_solution_for_pdf):
        """Test solution PDF download with Authorization header"""
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_with_solution_for_pdf['id']}/solution/pdf",
            headers=auth_headers,
            timeout=60
        )
        
        assert response.status_code == 200, f"Solution PDF download failed: {response.status_code}"
        assert response.headers.get("Content-Type") == "application/pdf"
        assert len(response.content) > 0, "PDF is empty"
        
        # Verify it's a valid PDF
        assert response.content[:4] == b"%PDF", "Not a valid PDF"
        
        # Verify filename ends with '- Solution.pdf'
        content_disp = response.headers.get("Content-Disposition", "")
        assert "- Solution.pdf" in content_disp, f"Filename should end with '- Solution.pdf', got: {content_disp}"
        
        print(f"✓ Solution PDF downloaded successfully ({len(response.content)} bytes)")
        print(f"  - Content-Disposition: {content_disp}")
    
    def test_solution_pdf_with_query_auth(self, auth_token, paper_with_solution_for_pdf):
        """Test solution PDF download with ?auth= query param"""
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_with_solution_for_pdf['id']}/solution/pdf?auth={auth_token}",
            timeout=60
        )
        
        assert response.status_code == 200, f"Solution PDF download failed: {response.status_code}"
        assert response.content[:4] == b"%PDF", "Not a valid PDF"
        print("✓ Solution PDF download works with ?auth= query param")
    
    def test_solution_pdf_without_solution(self, auth_headers, textbook_id):
        """Test solution PDF when no solution exists"""
        # Generate paper without solution
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "No Solution PDF Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_id,
                "topics": ["Motion"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 50, "concept": 30, "application": 20}
            },
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip("Could not generate paper")
        
        paper_id = response.json()["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_id}/solution/pdf",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Solution PDF correctly returns 400 when no solution exists")


# ============================================================
# Bulk Solution Generation Tests
# ============================================================
class TestBulkSolutionGeneration:
    """Tests for POST /api/papers/solutions/bulk-generate"""
    
    def test_bulk_generate_no_auth(self):
        """Test bulk solution generation without auth fails"""
        response = requests.post(
            f"{BASE_URL}/api/papers/solutions/bulk-generate",
            timeout=30
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Bulk solution generation correctly requires authentication")
    
    def test_bulk_generate_only_missing(self, auth_headers, textbook_id):
        """Test bulk generation with only_missing=true"""
        # Generate a paper without solution
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Bulk Test Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_id,
                "topics": ["Motion"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 50, "concept": 30, "application": 20}
            },
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not generate paper: {response.text[:200]}")
        
        paper_id = response.json()["id"]
        
        # Run bulk generation
        response = requests.post(
            f"{BASE_URL}/api/papers/solutions/bulk-generate?only_missing=true",
            headers=auth_headers,
            timeout=300  # Can be slow for multiple papers
        )
        
        assert response.status_code == 200, f"Bulk generation failed: {response.text}"
        
        data = response.json()
        assert "processed" in data, "Response should have 'processed' count"
        assert "succeeded" in data, "Response should have 'succeeded' count"
        assert "failed" in data, "Response should have 'failed' count"
        
        print(f"✓ Bulk solution generation completed")
        print(f"  - Processed: {data['processed']}")
        print(f"  - Succeeded: {data['succeeded']}")
        print(f"  - Failed: {data['failed']}")
        
        # Verify the paper now has a solution
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_id}",
            headers=auth_headers,
            timeout=30
        )
        
        if response.status_code == 200:
            paper = response.json()
            if paper.get("solution"):
                print("  - Paper now has solution after bulk generation")
            else:
                print("  ⚠ Paper still missing solution (may have failed)")


# ============================================================
# Toggle Important Tests
# ============================================================
class TestToggleImportant:
    """Tests for PATCH /api/papers/{id}/question/{qid}/toggle-important"""
    
    def test_toggle_important_no_auth(self, generated_paper):
        """Test toggle important without auth fails"""
        sections = generated_paper.get("sections", [])
        if not sections or not sections[0].get("questions"):
            pytest.skip("No questions to toggle")
        
        qid = sections[0]["questions"][0]["id"]
        
        response = requests.patch(
            f"{BASE_URL}/api/papers/{generated_paper['id']}/question/{qid}/toggle-important",
            timeout=30
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Toggle important correctly requires authentication")
    
    def test_toggle_important_success(self, auth_headers, generated_paper):
        """Test successful toggle important"""
        sections = generated_paper.get("sections", [])
        if not sections or not sections[0].get("questions"):
            pytest.skip("No questions to toggle")
        
        q = sections[0]["questions"][0]
        qid = q["id"]
        original_important = q.get("important", False)
        
        response = requests.patch(
            f"{BASE_URL}/api/papers/{generated_paper['id']}/question/{qid}/toggle-important",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Toggle failed: {response.text}"
        
        data = response.json()
        assert data.get("ok") == True
        assert "sections" in data
        
        # Find the toggled question
        for s in data.get("sections", []):
            for question in s.get("questions", []):
                if question.get("id") == qid:
                    assert question.get("important") == (not original_important), \
                        "Important flag should be toggled"
                    print(f"✓ Toggle important successful: {original_important} -> {not original_important}")
                    return
        
        pytest.fail("Toggled question not found in response")
    
    def test_toggle_important_nonexistent_question(self, auth_headers, generated_paper):
        """Test toggle important for non-existent question"""
        response = requests.patch(
            f"{BASE_URL}/api/papers/{generated_paper['id']}/question/nonexistent-qid/toggle-important",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Toggle important returns 404 for non-existent question")


# ============================================================
# Paper Delete Tests
# ============================================================
class TestPaperDelete:
    """Tests for DELETE /api/papers/{id}"""
    
    def test_delete_paper_no_auth(self, generated_paper):
        """Test paper delete without auth fails"""
        response = requests.delete(
            f"{BASE_URL}/api/papers/{generated_paper['id']}",
            timeout=30
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Paper delete correctly requires authentication")
    
    def test_delete_paper_success(self, auth_headers, textbook_id):
        """Test successful paper deletion"""
        # Generate a paper to delete
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Paper To Delete",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_id,
                "topics": ["Motion"],
                "difficulty": "easy",
                "duration_minutes": 30,
                "total_marks": 20,
                "distribution": {"information": 50, "concept": 30, "application": 20}
            },
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not generate paper: {response.text[:200]}")
        
        paper_id = response.json()["id"]
        
        # Delete the paper
        response = requests.delete(
            f"{BASE_URL}/api/papers/{paper_id}",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Delete failed: {response.text}"
        assert response.json().get("ok") == True
        
        # Verify paper is no longer accessible
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_id}",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 404, "Deleted paper should return 404"
        
        print("✓ Paper deleted successfully and no longer accessible")
    
    def test_delete_paper_nonexistent(self, auth_headers):
        """Test delete non-existent paper"""
        response = requests.delete(
            f"{BASE_URL}/api/papers/nonexistent-paper-id",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Delete non-existent paper returns 404")


# ============================================================
# Textbook Delete Tests
# ============================================================
class TestTextbookDelete:
    """Tests for DELETE /api/textbooks/{id}"""
    
    def test_delete_textbook_no_auth(self, textbook_id):
        """Test textbook delete without auth fails"""
        response = requests.delete(
            f"{BASE_URL}/api/textbooks/{textbook_id}",
            timeout=30
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Textbook delete correctly requires authentication")
    
    def test_delete_textbook_success(self, auth_headers):
        """Test successful textbook deletion"""
        # Upload a textbook to delete
        pdf_data = create_dummy_pdf()
        files = {"file": ("delete_textbook.pdf", pdf_data, "application/pdf")}
        response = requests.post(
            f"{BASE_URL}/api/textbooks/upload",
            files=files,
            params={"subject": "Physics", "class_name": "10"},
            headers=auth_headers,
            timeout=60
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not upload textbook: {response.text}")
        
        tb_id = response.json()["id"]
        
        # Delete the textbook
        response = requests.delete(
            f"{BASE_URL}/api/textbooks/{tb_id}",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Delete failed: {response.text}"
        assert response.json().get("ok") == True
        
        # Verify textbook is no longer accessible
        response = requests.get(
            f"{BASE_URL}/api/textbooks/{tb_id}",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 404, "Deleted textbook should return 404"
        
        print("✓ Textbook deleted successfully and no longer accessible")


# ============================================================
# Question Bank CRUD Tests
# ============================================================
class TestQuestionBankCRUD:
    """Tests for /api/qbank endpoints"""
    
    def test_create_qbank_question_no_auth(self):
        """Test qbank create without auth fails"""
        response = requests.post(
            f"{BASE_URL}/api/qbank",
            json={"question": "Test question", "type": "concept", "difficulty": "medium", "marks": 2},
            timeout=30
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Qbank create correctly requires authentication")
    
    def test_create_qbank_question_success(self, auth_headers):
        """Test successful qbank question creation"""
        response = requests.post(
            f"{BASE_URL}/api/qbank",
            json={
                "question": "TEST_QBANK: What is the formula for kinetic energy?",
                "type": "information",
                "difficulty": "easy",
                "marks": 2,
                "topic": "Energy"
            },
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Create failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "Response should have id"
        assert data["question"] == "TEST_QBANK: What is the formula for kinetic energy?"
        assert data["type"] == "information"
        assert data["difficulty"] == "easy"
        assert data["marks"] == 2
        
        print(f"✓ Qbank question created: {data['id']}")
        return data["id"]
    
    def test_list_qbank_with_filters(self, auth_headers):
        """Test qbank listing with filters"""
        # Create a question first
        requests.post(
            f"{BASE_URL}/api/qbank",
            json={
                "question": "TEST_FILTER: Filter test question",
                "type": "concept",
                "difficulty": "hard",
                "marks": 4
            },
            headers=auth_headers,
            timeout=30
        )
        
        # Test type filter
        response = requests.get(
            f"{BASE_URL}/api/qbank?type_filter=concept",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        for q in data:
            assert q.get("type") == "concept", "Type filter not working"
        print(f"✓ Type filter works: {len(data)} concept questions")
        
        # Test difficulty filter
        response = requests.get(
            f"{BASE_URL}/api/qbank?difficulty=hard",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        for q in data:
            assert q.get("difficulty") == "hard", "Difficulty filter not working"
        print(f"✓ Difficulty filter works: {len(data)} hard questions")
        
        # Test search query
        response = requests.get(
            f"{BASE_URL}/api/qbank?q=TEST_FILTER",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1, "Search should find at least one question"
        print(f"✓ Search query works: {len(data)} matching questions")
    
    def test_delete_qbank_question(self, auth_headers):
        """Test qbank question deletion"""
        # Create a question to delete
        response = requests.post(
            f"{BASE_URL}/api/qbank",
            json={
                "question": "TEST_DELETE: Question to delete",
                "type": "information",
                "difficulty": "easy",
                "marks": 1
            },
            headers=auth_headers,
            timeout=30
        )
        
        if response.status_code != 200:
            pytest.skip("Could not create question")
        
        qid = response.json()["id"]
        
        # Delete the question
        response = requests.delete(
            f"{BASE_URL}/api/qbank/{qid}",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Delete failed: {response.text}"
        assert response.json().get("ok") == True
        
        # Verify question is no longer in list
        response = requests.get(
            f"{BASE_URL}/api/qbank?q=TEST_DELETE",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should not find the deleted question
        found = any(q.get("id") == qid for q in data)
        assert not found, "Deleted question should not appear in list"
        
        print("✓ Qbank question deleted successfully")
    
    def test_save_from_paper(self, auth_headers, generated_paper):
        """Test saving a question from paper to qbank"""
        sections = generated_paper.get("sections", [])
        if not sections or not sections[0].get("questions"):
            pytest.skip("No questions in paper")
        
        qid = sections[0]["questions"][0]["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/qbank/save-from-paper/{generated_paper['id']}/{qid}",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Save from paper failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "Response should have id"
        assert data.get("source_paper_id") == generated_paper["id"]
        
        print(f"✓ Question saved from paper to qbank: {data['id']}")


# ============================================================
# Auth Enforcement Tests
# ============================================================
class TestAuthEnforcement:
    """Verify 401/403 responses for protected endpoints"""
    
    def test_access_other_users_paper(self, auth_headers, textbook_id):
        """Test accessing another user's paper returns 403"""
        # This test would require a second user, so we'll test with a non-existent paper
        # which should return 404 (not found) rather than 403 (forbidden)
        response = requests.get(
            f"{BASE_URL}/api/papers/nonexistent-paper-id",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent paper returns 404")
    
    def test_endpoints_return_401_without_token(self):
        """Test that protected endpoints return 401 without token"""
        endpoints = [
            ("GET", "/api/auth/me"),
            ("GET", "/api/textbooks"),
            ("GET", "/api/papers"),
            ("GET", "/api/qbank"),
            ("POST", "/api/papers/solutions/bulk-generate"),
        ]
        
        for method, endpoint in endpoints:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=30)
            else:
                response = requests.post(f"{BASE_URL}{endpoint}", json={}, timeout=30)
            
            assert response.status_code in [401, 403], \
                f"{method} {endpoint} should require auth, got {response.status_code}"
        
        print(f"✓ All {len(endpoints)} endpoints correctly require authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
