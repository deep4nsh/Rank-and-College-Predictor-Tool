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
