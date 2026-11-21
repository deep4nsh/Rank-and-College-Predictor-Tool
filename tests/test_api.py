from fastapi.testclient import TestClient
from backend.app.db.models import Base
from backend.app.db.session import engine
from backend.app.main import app

client = TestClient(app)


def setup_module():
    # Ensure fresh test tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_quick_estimate():
    res = client.get("/api/v1/predictor/quick-estimate?score=72.0&paper_code=CS&category=GEN")
    assert res.status_code == 200
    data = res.json()
    assert data["predicted_air"] < 500
    assert data["approx_gate_score"] >= 700
    assert len(data["coap_options"]) > 0


def test_end_to_end_exam_day_flow():
    # 1. Faculty Publishes Answer Key v1 for CS
    key_payload = {
        "paper_code": "CS",
        "version": 1,
        "key_type": "FACULTY_EXAM_DAY",
        "author_name": "PW CS Faculty Panel",
        "items": [
            {"question_id": "CS-Q1", "is_mta": False, "valid_options": [["B"]]},
            {"question_id": "CS-Q2", "is_mta": False, "valid_options": [["A", "C"]]},
            {"question_id": "CS-Q3", "is_mta": False, "nat_min": 15.0, "nat_max": 15.5},
            {"question_id": "CS-Q4", "is_mta": True},  # MTA
        ],
    }
    key_res = client.post("/api/v1/keys", json=key_payload)
    assert key_res.status_code == 200
    assert key_res.json()["status"] == "success"

    # 2. Student Submits Marked Paper on PW Portal
    sub_payload = {
        "student_phone": "9876543210",
        "student_name": "Aman Sharma",
        "student_email": "aman@example.com",
        "student_category": "GEN",
        "btech_percentage": 78.5,
        "candidate_age": 22,
        "has_valid_ncl": True,
        "pw_batch_id": "Parakram_2025_CS",
        "paper_code": "CS",
        "session_id": 1,
        "responses": [
            {"question_id": "CS-Q1", "status": "ATTEMPTED", "marked_options": ["B"]},
            {"question_id": "CS-Q2", "status": "ATTEMPTED", "marked_options": ["A", "C"]},
            {"question_id": "CS-Q3", "status": "ATTEMPTED", "nat_value": "15.2"},
            {"question_id": "CS-Q4", "status": "SKIPPED"},
        ],
    }
    sub_res = client.post("/api/v1/submissions", json=sub_payload)
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["status"] == "success"
    assert sub_data["raw_score_total"] > 0
    assert sub_data["predicted_air"] > 0

    # 3. Counsellor Checks Dashboard
    counsellor_res = client.get("/api/v1/counsellor/students?search=9876543210")
    assert counsellor_res.status_code == 200
    c_data = counsellor_res.json()
    assert c_data["total"] == 1
    assert c_data["students"][0]["student_name"] == "Aman Sharma"

    # 4. Counsellor Generates WhatsApp Summary
    wa_res = client.get("/api/v1/counsellor/students/9876543210/whatsapp-summary")
    assert wa_res.status_code == 200
    wa_data = wa_res.json()
    assert "Aman Sharma" in wa_data["whatsapp_text"]
    assert "PW GATE Academic & Counselling Diagnostic" in wa_data["whatsapp_text"]

    # 5. Later: IIT Releases Official Key v2 (e.g. Q3 NAT accepted range shifts)
    official_key_payload = {
        "paper_code": "CS",
        "version": 2,
        "key_type": "OFFICIAL_IIT",
        "author_name": "IIT Official Master Key",
        "items": [
            {"question_id": "CS-Q1", "is_mta": False, "valid_options": [["B"]]},
            {"question_id": "CS-Q2", "is_mta": False, "valid_options": [["A", "C"]]},
            {"question_id": "CS-Q3", "is_mta": False, "nat_min": 15.0, "nat_max": 15.5},
            {"question_id": "CS-Q4", "is_mta": True},
        ],
    }
    official_key_res = client.post("/api/v1/keys", json=official_key_payload)
    assert official_key_res.status_code == 200
    new_key_id = official_key_res.json()["key_id"]

    # Trigger batch re-evaluation against new official key
    re_eval_res = client.post(f"/api/v1/keys/{new_key_id}/re-evaluate")
    assert re_eval_res.status_code == 200
    re_eval_data = re_eval_res.json()
    assert re_eval_data["status"] == "success"
    assert re_eval_data["re_evaluated_count"] == 1
    assert re_eval_data["key_version"] == 2
