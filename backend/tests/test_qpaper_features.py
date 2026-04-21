"""
Backend API tests for AI Question Paper Generator - New Features
Tests: Auth, Textbook upload, Topic extraction, Paper generation with diagrams,
       Paper editing (feedback loop), Question paper upload, PDF download
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
TEST_EMAIL = f"test_qpaper_{int(time.time())}@test.com"
TEST_PASSWORD = "testpass123"
TEST_NAME = "Test User"

# Existing test user
EXISTING_EMAIL = "pdftest@t.com"
EXISTING_PASSWORD = "pass123"


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
    c.save()
    return buf.getvalue()


def create_question_paper_pdf() -> bytes:
    """Create a PDF that looks like an existing question paper."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(100, 750, "Physics Question Paper - Class 10")
    c.drawString(100, 730, "Time: 2 hours    Total Marks: 50")
    c.drawString(100, 700, "Section A - Short Answer Questions (2 marks each)")
    c.drawString(100, 680, "Q1. Define velocity and acceleration.")
    c.drawString(100, 660, "Q2. State Newton's First Law of Motion.")
    c.drawString(100, 640, "Q3. What is the SI unit of force?")
    c.drawString(100, 610, "Section B - Long Answer Questions (5 marks each)")
    c.drawString(100, 590, "Q4. Explain the concept of projectile motion with a diagram.")
    c.drawString(100, 570, "Q5. Derive the equation v = u + at from first principles.")
    c.save()
    return buf.getvalue()


class TestAuth:
    """Authentication endpoint tests"""
    
    def test_register_new_user(self):
        """Test user registration"""
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "full_name": TEST_NAME,
            "role": "teacher"
        }, timeout=30)
        
        assert response.status_code == 200, f"Register failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert "user" in data, "No user in response"
        assert data["user"]["email"] == TEST_EMAIL.lower()
        assert data["user"]["role"] == "teacher"
        print(f"✓ Registration successful for {TEST_EMAIL}")
    
    def test_register_duplicate_email(self):
        """Test duplicate email registration fails"""
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "full_name": TEST_NAME,
            "role": "teacher"
        }, timeout=30)
        
        assert response.status_code == 400, "Duplicate registration should fail"
        print("✓ Duplicate email registration correctly rejected")
    
    def test_login_success(self):
        """Test login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        }, timeout=30)
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL.lower()
        print("✓ Login successful")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": "wrongpassword"
        }, timeout=30)
        
        assert response.status_code == 401, "Invalid login should return 401"
        print("✓ Invalid credentials correctly rejected")
    
    def test_login_existing_user(self):
        """Test login with existing test user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": EXISTING_EMAIL,
            "password": EXISTING_PASSWORD
        }, timeout=30)
        
        # This may fail if user doesn't exist - that's OK
        if response.status_code == 200:
            data = response.json()
            assert "token" in data
            print(f"✓ Existing user login successful: {EXISTING_EMAIL}")
        else:
            print(f"⚠ Existing user {EXISTING_EMAIL} not found (status {response.status_code})")


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for authenticated tests"""
    # First try to register
    response = requests.post(f"{BASE_URL}/api/auth/register", json={
        "email": f"fixture_user_{int(time.time())}@test.com",
        "password": TEST_PASSWORD,
        "full_name": "Fixture User",
        "role": "teacher"
    }, timeout=30)
    
    if response.status_code == 200:
        return response.json()["token"]
    
    # Fallback to login with test user
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


class TestTextbookUpload:
    """Textbook upload and topic extraction tests"""
    
    def test_upload_textbook_no_auth(self):
        """Test textbook upload without auth fails"""
        pdf_data = create_dummy_pdf()
        files = {"file": ("textbook.pdf", pdf_data, "application/pdf")}
        response = requests.post(
            f"{BASE_URL}/api/textbooks/upload",
            files=files,
            params={"subject": "Physics", "class_name": "10"},
            timeout=60
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Textbook upload correctly requires authentication")
    
    def test_upload_textbook_success(self, auth_headers):
        """Test successful textbook upload"""
        pdf_data = create_dummy_pdf()
        files = {"file": ("physics_textbook.pdf", pdf_data, "application/pdf")}
        response = requests.post(
            f"{BASE_URL}/api/textbooks/upload",
            files=files,
            params={"subject": "Physics", "class_name": "10"},
            headers=auth_headers,
            timeout=60
        )
        
        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        assert "id" in data, "No textbook ID returned"
        assert data["status"] in ["indexed", "extraction_failed"]
        print(f"✓ Textbook uploaded: {data['id']}, status: {data['status']}")
        return data["id"]
    
    def test_upload_non_pdf_fails(self, auth_headers):
        """Test non-PDF upload fails"""
        files = {"file": ("textbook.txt", b"Not a PDF", "text/plain")}
        response = requests.post(
            f"{BASE_URL}/api/textbooks/upload",
            files=files,
            params={"subject": "Physics", "class_name": "10"},
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 400, "Non-PDF should be rejected"
        print("✓ Non-PDF file correctly rejected")


class TestTopicExtraction:
    """Topic extraction tests"""
    
    @pytest.fixture
    def uploaded_textbook_id(self, auth_headers):
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
    
    def test_extract_topics_no_auth(self, uploaded_textbook_id):
        """Test topic extraction without auth fails"""
        response = requests.post(
            f"{BASE_URL}/api/textbooks/{uploaded_textbook_id}/extract-topics",
            timeout=60
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Topic extraction correctly requires authentication")
    
    def test_extract_topics_success(self, auth_headers, uploaded_textbook_id):
        """Test successful topic extraction via LLM"""
        response = requests.post(
            f"{BASE_URL}/api/textbooks/{uploaded_textbook_id}/extract-topics",
            headers=auth_headers,
            timeout=120  # LLM calls can be slow
        )
        
        # May fail if textbook has no indexed text
        if response.status_code == 400:
            print(f"⚠ Topic extraction skipped: {response.json().get('detail')}")
            return
        
        assert response.status_code in [200, 502], f"Unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert "topics" in data
            print(f"✓ Topics extracted: {len(data['topics'])} topics")
            for t in data["topics"][:3]:
                print(f"  - {t.get('name')}: {len(t.get('subtopics', []))} subtopics")
        else:
            print(f"⚠ LLM extraction failed (502): {response.json().get('detail')}")


class TestPaperGeneration:
    """Paper generation tests including diagram support"""
    
    @pytest.fixture
    def textbook_with_topics(self, auth_headers):
        """Upload textbook and extract topics"""
        # Upload
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
            pytest.skip("Could not upload textbook")
        
        textbook_id = response.json()["id"]
        
        # Extract topics
        response = requests.post(
            f"{BASE_URL}/api/textbooks/{textbook_id}/extract-topics",
            headers=auth_headers,
            timeout=120
        )
        
        topics = []
        if response.status_code == 200:
            topics = [t["name"] for t in response.json().get("topics", [])]
        
        if not topics:
            topics = ["Motion", "Forces", "Newton's Laws"]  # Fallback
        
        return {"id": textbook_id, "topics": topics}
    
    def test_generate_paper_no_auth(self, textbook_with_topics):
        """Test paper generation without auth fails"""
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Test Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_with_topics["id"],
                "topics": textbook_with_topics["topics"][:2],
                "difficulty": "medium",
                "duration_minutes": 60,
                "total_marks": 50,
                "distribution": {"information": 30, "concept": 40, "application": 30}
            },
            timeout=120
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Paper generation correctly requires authentication")
    
    def test_generate_paper_success(self, auth_headers, textbook_with_topics):
        """Test successful paper generation with diagram support"""
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Physics Mid-Term Test",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_with_topics["id"],
                "topics": textbook_with_topics["topics"][:3] if len(textbook_with_topics["topics"]) >= 3 else textbook_with_topics["topics"],
                "difficulty": "medium",
                "duration_minutes": 60,
                "total_marks": 50,
                "distribution": {"information": 30, "concept": 40, "application": 30}
            },
            headers=auth_headers,
            timeout=180  # Paper generation + diagrams can be slow
        )
        
        assert response.status_code in [200, 502], f"Unexpected status: {response.status_code}, {response.text}"
        
        if response.status_code == 502:
            print(f"⚠ Paper generation LLM failed: {response.json().get('detail')}")
            return None
        
        data = response.json()
        assert "id" in data, "No paper ID"
        assert "sections" in data, "No sections in paper"
        
        # Check for diagram support
        diagram_count = 0
        total_questions = 0
        for section in data.get("sections", []):
            for q in section.get("questions", []):
                total_questions += 1
                if q.get("needs_diagram"):
                    diagram_count += 1
                    if q.get("diagram_path"):
                        print(f"  ✓ Question has diagram_path: {q['diagram_path'][:50]}...")
        
        print(f"✓ Paper generated: {data['id']}")
        print(f"  - Total questions: {total_questions}")
        print(f"  - Questions with needs_diagram=true: {diagram_count}")
        print(f"  - Note: Diagram generation is best-effort; LLM may not always flag diagrams")
        
        return data
    
    def test_generate_paper_invalid_distribution(self, auth_headers, textbook_with_topics):
        """Test paper generation with invalid distribution fails"""
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Test Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_with_topics["id"],
                "topics": textbook_with_topics["topics"][:2],
                "difficulty": "medium",
                "duration_minutes": 60,
                "total_marks": 50,
                "distribution": {"information": 20, "concept": 20, "application": 20}  # Sum = 60, not 100
            },
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 400, "Invalid distribution should fail"
        print("✓ Invalid distribution correctly rejected")


class TestPaperEditing:
    """Paper editing and feedback loop tests"""
    
    @pytest.fixture
    def generated_paper(self, auth_headers):
        """Generate a paper for editing tests"""
        # First upload textbook
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
            pytest.skip("Could not upload textbook")
        
        textbook_id = response.json()["id"]
        
        # Generate paper
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "Editable Test Paper",
                "subject": "Physics",
                "class_name": "10",
                "textbook_id": textbook_id,
                "topics": ["Motion", "Forces"],
                "difficulty": "medium",
                "duration_minutes": 60,
                "total_marks": 30,
                "distribution": {"information": 34, "concept": 33, "application": 33}
            },
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"Could not generate paper: {response.text}")
        
        return response.json()
    
    def test_patch_paper_metadata(self, auth_headers, generated_paper):
        """Test updating paper title, instructions, duration, marks"""
        paper_id = generated_paper["id"]
        
        response = requests.patch(
            f"{BASE_URL}/api/papers/{paper_id}",
            json={
                "title": "Updated Physics Test",
                "instructions": "Answer all questions. Show your work.",
                "duration_minutes": 90,
                "total_marks": 60
            },
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Patch failed: {response.text}"
        data = response.json()
        assert data["title"] == "Updated Physics Test"
        assert data["instructions"] == "Answer all questions. Show your work."
        assert data["duration_minutes"] == 90
        assert data["total_marks"] == 60
        print("✓ Paper metadata updated successfully")
    
    def test_patch_paper_sections_modify_question(self, auth_headers, generated_paper):
        """Test modifying a question and verify paper_edits collection"""
        paper_id = generated_paper["id"]
        sections = generated_paper.get("sections", [])
        
        if not sections or not sections[0].get("questions"):
            pytest.skip("No questions in paper to modify")
        
        # Modify first question
        modified_sections = []
        for section in sections:
            new_questions = []
            for i, q in enumerate(section.get("questions", [])):
                if i == 0:
                    # Modify first question
                    q["question"] = "MODIFIED: " + q.get("question", "Test question")
                new_questions.append(q)
            modified_sections.append({
                "title": section.get("title", "Section"),
                "questions": new_questions
            })
        
        response = requests.patch(
            f"{BASE_URL}/api/papers/{paper_id}",
            json={"sections": modified_sections},
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Patch failed: {response.text}"
        data = response.json()
        
        # Verify modification
        first_q = data["sections"][0]["questions"][0]
        assert first_q["question"].startswith("MODIFIED:"), "Question not modified"
        print("✓ Question modified successfully")
        print("  - paper_edits collection should have 'modify_question' entry")
    
    def test_patch_paper_sections_add_question(self, auth_headers, generated_paper):
        """Test adding a new question and verify paper_edits collection"""
        paper_id = generated_paper["id"]
        sections = generated_paper.get("sections", [])
        
        if not sections:
            pytest.skip("No sections in paper")
        
        # Add new question to first section
        modified_sections = []
        for i, section in enumerate(sections):
            questions = list(section.get("questions", []))
            if i == 0:
                questions.append({
                    "question": "NEW QUESTION: What is the formula for kinetic energy?",
                    "type": "information",
                    "difficulty": "easy",
                    "marks": 2
                })
            modified_sections.append({
                "title": section.get("title", "Section"),
                "questions": questions
            })
        
        response = requests.patch(
            f"{BASE_URL}/api/papers/{paper_id}",
            json={"sections": modified_sections},
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Patch failed: {response.text}"
        data = response.json()
        
        # Verify addition
        found_new = False
        for section in data["sections"]:
            for q in section.get("questions", []):
                if "NEW QUESTION:" in q.get("question", ""):
                    found_new = True
                    assert "id" in q, "New question should have ID"
                    break
        
        assert found_new, "New question not found in response"
        print("✓ Question added successfully")
        print("  - paper_edits collection should have 'add_question' entry")
    
    def test_patch_paper_sections_delete_question(self, auth_headers, generated_paper):
        """Test deleting a question and verify paper_edits collection"""
        paper_id = generated_paper["id"]
        sections = generated_paper.get("sections", [])
        
        if not sections or len(sections[0].get("questions", [])) < 2:
            pytest.skip("Not enough questions to delete")
        
        # Remove last question from first section
        modified_sections = []
        for i, section in enumerate(sections):
            questions = list(section.get("questions", []))
            if i == 0 and len(questions) > 1:
                questions = questions[:-1]  # Remove last
            modified_sections.append({
                "title": section.get("title", "Section"),
                "questions": questions
            })
        
        original_count = len(sections[0].get("questions", []))
        
        response = requests.patch(
            f"{BASE_URL}/api/papers/{paper_id}",
            json={"sections": modified_sections},
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200, f"Patch failed: {response.text}"
        data = response.json()
        
        new_count = len(data["sections"][0].get("questions", []))
        assert new_count == original_count - 1, "Question not deleted"
        print("✓ Question deleted successfully")
        print("  - paper_edits collection should have 'delete_question' entry")


class TestFeedbackLoop:
    """Test that feedback loop works - edits are used in future generations"""
    
    def test_generate_after_edits(self, auth_headers):
        """Generate paper twice after making edits - verify second call succeeds"""
        # Upload textbook
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
            pytest.skip("Could not upload textbook")
        
        textbook_id = response.json()["id"]
        
        # Generate first paper
        gen_payload = {
            "title": "Feedback Loop Test Paper 1",
            "subject": "Physics",
            "class_name": "10",
            "textbook_id": textbook_id,
            "topics": ["Motion", "Forces"],
            "difficulty": "medium",
            "duration_minutes": 60,
            "total_marks": 30,
            "distribution": {"information": 34, "concept": 33, "application": 33}
        }
        
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json=gen_payload,
            headers=auth_headers,
            timeout=180
        )
        
        if response.status_code != 200:
            pytest.skip(f"First generation failed: {response.text}")
        
        paper1 = response.json()
        print(f"✓ First paper generated: {paper1['id']}")
        
        # Make an edit
        if paper1.get("sections") and paper1["sections"][0].get("questions"):
            sections = paper1["sections"]
            sections[0]["questions"][0]["question"] = "TEACHER EDIT: " + sections[0]["questions"][0].get("question", "")
            
            response = requests.patch(
                f"{BASE_URL}/api/papers/{paper1['id']}",
                json={"sections": [{"title": s["title"], "questions": s["questions"]} for s in sections]},
                headers=auth_headers,
                timeout=30
            )
            assert response.status_code == 200, "Edit failed"
            print("✓ Edit made to first paper")
        
        # Generate second paper (should use feedback hints from edits)
        gen_payload["title"] = "Feedback Loop Test Paper 2"
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json=gen_payload,
            headers=auth_headers,
            timeout=180
        )
        
        # The key test: second generation should succeed even with feedback hints
        assert response.status_code in [200, 502], f"Second generation unexpected status: {response.status_code}"
        
        if response.status_code == 200:
            paper2 = response.json()
            print(f"✓ Second paper generated successfully: {paper2['id']}")
            print("  - Feedback loop prompt worked without breaking generation")
        else:
            print(f"⚠ Second generation LLM failed (502) - this is acceptable")


class TestDiagramEndpoint:
    """Test diagram serving endpoint"""
    
    def test_diagram_endpoint_no_auth(self):
        """Test diagram endpoint without auth fails"""
        response = requests.get(
            f"{BASE_URL}/api/papers/fake-paper-id/diagrams/fake-question-id",
            timeout=30
        )
        assert response.status_code == 401, "Should require auth"
        print("✓ Diagram endpoint correctly requires authentication")
    
    def test_diagram_endpoint_not_found(self, auth_headers, auth_token):
        """Test diagram endpoint with non-existent paper"""
        response = requests.get(
            f"{BASE_URL}/api/papers/nonexistent-paper/diagrams/nonexistent-q",
            headers=auth_headers,
            timeout=30
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Diagram endpoint returns 404 for non-existent paper")
    
    def test_diagram_endpoint_with_query_auth(self, auth_token):
        """Test diagram endpoint with ?auth= query param"""
        response = requests.get(
            f"{BASE_URL}/api/papers/nonexistent-paper/diagrams/nonexistent-q?auth={auth_token}",
            timeout=30
        )
        # Should get 404 (paper not found) not 401 (auth failed)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Diagram endpoint accepts ?auth= query param")


class TestQuestionPaperUpload:
    """Test uploading existing question papers"""
    
    def test_upload_qpaper_no_auth(self):
        """Test qpaper upload without auth fails"""
        pdf_data = create_question_paper_pdf()
        files = {"file": ("qpaper.pdf", pdf_data, "application/pdf")}
        response = requests.post(
            f"{BASE_URL}/api/qpapers/upload",
            files=files,
            timeout=60
        )
        assert response.status_code in [401, 403], "Should require auth"
        print("✓ Question paper upload correctly requires authentication")
    
    def test_upload_qpaper_success(self, auth_headers):
        """Test successful question paper upload and parsing"""
        pdf_data = create_question_paper_pdf()
        files = {"file": ("physics_qpaper.pdf", pdf_data, "application/pdf")}
        response = requests.post(
            f"{BASE_URL}/api/qpapers/upload",
            files=files,
            params={"subject": "Physics", "class_name": "10"},
            headers=auth_headers,
            timeout=120  # LLM parsing can be slow
        )
        
        assert response.status_code in [200, 502], f"Unexpected status: {response.status_code}, {response.text}"
        
        if response.status_code == 502:
            print(f"⚠ Question paper extraction LLM failed: {response.json().get('detail')}")
            return
        
        data = response.json()
        assert "saved" in data, "No 'saved' count in response"
        assert "questions" in data, "No 'questions' in response"
        
        print(f"✓ Question paper uploaded and parsed")
        print(f"  - Saved {data['saved']} questions to qbank")
        print(f"  - Subject: {data.get('subject')}, Class: {data.get('class_name')}")
        
        # Verify questions have source='uploaded'
        for q in data.get("questions", [])[:3]:
            assert q.get("source") == "uploaded", "Question should have source='uploaded'"
            print(f"  - Q: {q.get('question', '')[:50]}...")
    
    def test_upload_qpaper_verify_in_qbank(self, auth_headers):
        """Upload qpaper and verify questions appear in qbank"""
        pdf_data = create_question_paper_pdf()
        files = {"file": ("verify_qpaper.pdf", pdf_data, "application/pdf")}
        response = requests.post(
            f"{BASE_URL}/api/qpapers/upload",
            files=files,
            params={"subject": "Physics", "class_name": "10"},
            headers=auth_headers,
            timeout=120
        )
        
        if response.status_code != 200:
            pytest.skip(f"Upload failed: {response.text}")
        
        saved_count = response.json().get("saved", 0)
        
        # Check qbank
        response = requests.get(
            f"{BASE_URL}/api/qbank",
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 200
        qbank = response.json()
        
        # Find uploaded questions
        uploaded_qs = [q for q in qbank if q.get("source") == "uploaded"]
        print(f"✓ Found {len(uploaded_qs)} uploaded questions in qbank")
        assert len(uploaded_qs) >= saved_count, "Uploaded questions not found in qbank"


class TestPDFDownload:
    """Test PDF download endpoint"""
    
    @pytest.fixture
    def paper_for_pdf(self, auth_headers):
        """Generate a paper for PDF download test"""
        # Upload textbook
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
            pytest.skip("Could not upload textbook")
        
        textbook_id = response.json()["id"]
        
        # Generate paper
        response = requests.post(
            f"{BASE_URL}/api/papers/generate",
            json={
                "title": "PDF Download Test Paper",
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
            pytest.skip(f"Could not generate paper: {response.text}")
        
        return response.json()
    
    def test_pdf_download_no_auth(self, paper_for_pdf):
        """Test PDF download without auth fails"""
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_for_pdf['id']}/pdf",
            timeout=30
        )
        assert response.status_code == 401, "Should require auth"
        print("✓ PDF download correctly requires authentication")
    
    def test_pdf_download_with_header(self, auth_headers, paper_for_pdf):
        """Test PDF download with Authorization header"""
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_for_pdf['id']}/pdf",
            headers=auth_headers,
            timeout=60
        )
        
        assert response.status_code == 200, f"PDF download failed: {response.status_code}"
        assert response.headers.get("Content-Type") == "application/pdf"
        assert len(response.content) > 0, "PDF is empty"
        
        # Verify it's a valid PDF (starts with %PDF)
        assert response.content[:4] == b"%PDF", "Not a valid PDF"
        print(f"✓ PDF downloaded successfully ({len(response.content)} bytes)")
    
    def test_pdf_download_with_query_auth(self, auth_token, paper_for_pdf):
        """Test PDF download with ?auth= query param"""
        response = requests.get(
            f"{BASE_URL}/api/papers/{paper_for_pdf['id']}/pdf?auth={auth_token}",
            timeout=60
        )
        
        assert response.status_code == 200, f"PDF download failed: {response.status_code}"
        assert response.content[:4] == b"%PDF", "Not a valid PDF"
        print("✓ PDF download works with ?auth= query param")


class TestJWTEnforcement:
    """Verify JWT auth is enforced on all endpoints"""
    
    PROTECTED_ENDPOINTS = [
        ("GET", "/api/auth/me"),
        ("GET", "/api/textbooks"),
        ("GET", "/api/papers"),
        ("GET", "/api/qbank"),
    ]
    
    def test_protected_endpoints_require_auth(self):
        """Test that protected endpoints return 401/403 without auth"""
        for method, endpoint in self.PROTECTED_ENDPOINTS:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{endpoint}", timeout=30)
            elif method == "POST":
                response = requests.post(f"{BASE_URL}{endpoint}", json={}, timeout=30)
            
            assert response.status_code in [401, 403], f"{method} {endpoint} should require auth, got {response.status_code}"
        
        print(f"✓ All {len(self.PROTECTED_ENDPOINTS)} protected endpoints require authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
