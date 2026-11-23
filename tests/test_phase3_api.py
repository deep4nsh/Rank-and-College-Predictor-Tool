from fastapi.testclient import TestClient
from backend.app.db.models import Base
from backend.app.db.session import engine
from backend.app.main import app

client = TestClient(app)


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_serve_index_html():
    res = client.get("/")
    assert res.status_code == 200
    assert "Physics Wallah" in res.text
    assert "Question Palette" in res.text


def test_api_health_endpoint():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_sample_paper_blueprint():
    res = client.get("/api/v1/ingest/sample-paper/CS")
    assert res.status_code == 200
    data = res.json()
    assert data["paper_code"] == "CS"
    assert data["total_questions"] == 65
    assert data["total_marks"] == 100
    assert len(data["questions"]) == 65
    # Verify section split
    apt_questions = [q for q in data["questions"] if q["section"] == "APTITUDE"]
    core_questions = [q for q in data["questions"] if q["section"] == "CORE"]
    assert len(apt_questions) == 10
    assert len(core_questions) == 55


def test_digialm_html_parsing_and_submission_pipeline():
    # 1. Publish active CS key
    key_payload = {
        "paper_code": "CS",
        "version": 10,
        "key_type": "FACULTY_EXAM_DAY",
        "author_name": "PW Faculty",
        "items": [
            {"question_id": "823251501", "question_number": 1, "section": "APTITUDE", "question_type": "MCQ", "marks_correct": 1.0, "valid_options": [["B"]]},
            {"question_id": "823251502", "question_number": 2, "section": "CORE", "question_type": "MSQ", "marks_correct": 2.0, "valid_options": [["A", "C"]]},
            {"question_id": "823251503", "question_number": 3, "section": "CORE", "question_type": "NAT", "marks_correct": 2.0, "nat_min": 24.0, "nat_max": 25.0},
        ],
    }
    client.post("/api/v1/keys", json=key_payload)

    raw_html = """
    <table>
      <tr><td>Participant Name</td><td>Shreya Ghoshal</td></tr>
      <tr><td>Participant ID</td><td>CS25S38123456</td></tr>
      <tr><td>Subject</td><td>CS Computer Science and Information Technology</td></tr>
    </table>
    <table class="menu-tbl">
      <tr><td>Question ID :</td><td>823251501</td></tr>
      <tr><td>Question Type :</td><td>MCQ</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Chosen Option :</td><td>2</td></tr>
    </table>
    <table class="menu-tbl">
      <tr><td>Question ID :</td><td>823251502</td></tr>
      <tr><td>Question Type :</td><td>MSQ</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Chosen Option :</td><td>1, 3</td></tr>
    </table>
    <table class="menu-tbl">
      <tr><td>Question ID :</td><td>823251503</td></tr>
      <tr><td>Question Type :</td><td>NAT</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Given Answer :</td><td>24.8</td></tr>
    </table>
    """

    # 2. Test parse-only endpoint
    res_parse = client.post("/api/v1/ingest/response-sheet/parse-html", json={"html_content": raw_html})
    assert res_parse.status_code == 200
    parse_data = res_parse.json()
    assert parse_data["candidate_name"] == "Shreya Ghoshal"
    assert parse_data["paper_code"] == "CS"
    assert parse_data["total_questions"] == 3
    assert parse_data["attempted_count"] == 3

    # 3. Test submit & evaluate endpoint
    submit_payload = {
        "html_content": raw_html,
        "student_phone": "9898123456",
        "student_category": "GEN",
        "btech_percentage": 78.0,
        "candidate_age": 22,
    }
    res_sub = client.post("/api/v1/ingest/response-sheet/submit", json=submit_payload)
    assert res_sub.status_code == 200
    sub_data = res_sub.json()
    assert sub_data["raw_score_total"] == 5.0  # 1.0 (Q1) + 2.0 (Q2) + 2.0 (Q3)
    assert sub_data["marks_lost_to_negatives"] == 0.0

    # 4. Verify Counsellor PDF streaming endpoint
    res_pdf = client.get("/api/v1/counsellor/students/9898123456/pdf")
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"
    assert res_pdf.content.startswith(b"%PDF")


def test_empty_or_invalid_html_rejection():
    """
    Edge case: Blank or non-exam HTML should be rejected with HTTP 400.
    """
    submit_payload = {
        "html_content": "<html><body><h1>Random Blog Post Without Exam Questions</h1></body></html>",
        "student_phone": "9898123457",
        "student_category": "GEN",
    }
    res = client.post("/api/v1/ingest/response-sheet/submit", json=submit_payload)
    assert res.status_code == 400
    assert "No question panels found" in res.json()["detail"]


def test_sample_paper_branch_and_session_diversity():
    """
    Verifies that different branches and sessions receive authentic, distinct questions,
    with options for MCQ/MSQ and units for NAT.
    """
    # 1. CS Session 1 vs Session 2
    res_cs1 = client.get("/api/v1/ingest/sample-paper/CS?session_id=1")
    assert res_cs1.status_code == 200
    cs1_data = res_cs1.json()
    assert cs1_data["total_questions"] == 65
    assert cs1_data["session_id"] == 1

    res_cs2 = client.get("/api/v1/ingest/sample-paper/CS?session_id=2")
    assert res_cs2.status_code == 200
    cs2_data = res_cs2.json()
    assert cs2_data["total_questions"] == 65
    assert cs2_data["session_id"] == 2

    # Assert distinct questions between sessions
    assert cs1_data["questions"][0]["question_text"] != cs2_data["questions"][0]["question_text"]
    assert cs1_data["questions"][10]["question_text"] != cs2_data["questions"][10]["question_text"]

    # Assert option texts exist for MCQ/MSQ
    q_mcq = cs1_data["questions"][0]
    assert q_mcq["question_type"] == "MCQ"
    assert "options" in q_mcq and "A" in q_mcq["options"] and "B" in q_mcq["options"]

    # 2. Test DA (Data Science & AI)
    res_da = client.get("/api/v1/ingest/sample-paper/DA?session_id=1")
    assert res_da.status_code == 200
    da_data = res_da.json()
    assert da_data["total_questions"] == 65
    # Verify DA-specific tags
    da_tags = {q.get("subject_tag") for q in da_data["questions"]}
    assert "Machine Learning" in da_tags or "Linear Algebra" in da_tags

    # 3. Test ME (Mechanical)
    res_me = client.get("/api/v1/ingest/sample-paper/ME?session_id=1")
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert me_data["total_questions"] == 65
    me_tags = {q.get("subject_tag") for q in me_data["questions"]}
    assert "Thermodynamics" in me_tags or "Fluid Mechanics" in me_tags


def test_sample_paper_interactive_student_submission():
    """
    Verifies that a student can take and submit an exam directly from the CBT portal
    for any branch (e.g. ME) and receive immediate evaluation and admissions prediction
    without manual pre-configuration of answer keys.
    """
    # Fetch ME paper blueprint
    paper_res = client.get("/api/v1/ingest/sample-paper/ME?session_id=1")
    assert paper_res.status_code == 200
    paper_data = paper_res.json()
    q1 = paper_data["questions"][0]  # Aptitude Q1
    q11 = paper_data["questions"][10] # Core Q11 (Carnot Engine, 50% = Option A)

    sub_payload = {
        "student_phone": "9811122233",
        "student_name": "Karan Malhotra",
        "student_email": "karan.me@example.com",
        "student_category": "GEN",
        "btech_percentage": 76.0,
        "candidate_age": 23,
        "has_valid_ncl": True,
        "pw_batch_id": "PW_ME_CBT",
        "paper_code": "ME",
        "session_id": 1,
        "responses": [
            {"question_id": q1["question_id"], "status": "ATTEMPTED", "marked_options": ["B"]},
            {"question_id": q11["question_id"], "status": "ATTEMPTED", "marked_options": ["A"]},
        ],
    }

    sub_res = client.post("/api/v1/submissions", json=sub_payload)
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["status"] == "success"
    assert sub_data["raw_score_total"] > 0
    assert sub_data["predicted_air"] > 0
    assert "coap_options" in sub_data
    assert "psu_options" in sub_data
