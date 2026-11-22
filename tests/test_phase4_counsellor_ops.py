from fastapi.testclient import TestClient
from backend.app.db.models import Base
from backend.app.db.session import engine
from backend.app.main import app

client = TestClient(app)


def setup_module():
    Base.metadata.create_all(bind=engine)


def test_counsellor_call_logging_and_history():
    # 1. Create a student submission
    key_payload = {
        "paper_code": "CS",
        "version": 99,
        "key_type": "FACULTY_EXAM_DAY",
        "author_name": "PW Faculty",
        "items": [
            {"question_id": "CS-Q1", "question_number": 1, "section": "APTITUDE", "question_type": "MCQ", "marks_correct": 1.0, "valid_options": [["B"]]},
            {"question_id": "CS-Q2", "question_number": 2, "section": "CORE", "question_type": "MCQ", "marks_correct": 2.0, "valid_options": [["A"]]},
        ],
    }
    client.post("/api/v1/keys", json=key_payload)

    phone = "9876500001"
    sub_payload = {
        "student_phone": phone,
        "student_name": "Rohan Mehra",
        "student_email": "rohan@example.com",
        "student_category": "GEN",
        "paper_code": "CS",
        "session_id": 1,
        "responses": [
            {"question_id": "CS-Q1", "status": "ATTEMPTED", "marked_options": ["B"]},  # +1
            {"question_id": "CS-Q2", "status": "ATTEMPTED", "marked_options": ["C"]},  # wrong -> -2/3 marks
        ],
    }
    res_sub = client.post("/api/v1/submissions", json=sub_payload)
    assert res_sub.status_code == 200

    # 2. Verify initial call disposition is PENDING
    res_prof = client.get(f"/api/v1/counsellor/students/{phone}")
    assert res_prof.status_code == 200
    assert res_prof.json()["call_disposition"] == "PENDING"
    assert len(res_prof.json()["call_history"]) == 0

    # 3. Log first call
    log_payload_1 = {
        "counsellor_name": "Pooja Sharma",
        "call_disposition": "CONNECTED_FOLLOW_UP",
        "notes": "Candidate was travelling. Asked to call back tomorrow afternoon.",
        "follow_up_date": "2026-11-23",
    }
    res_log1 = client.post(f"/api/v1/counsellor/students/{phone}/call-log", json=log_payload_1)
    assert res_log1.status_code == 200
    log1_data = res_log1.json()
    assert log1_data["call_disposition"] == "CONNECTED_FOLLOW_UP"
    assert log1_data["counsellor_name"] == "Pooja Sharma"

    # 4. Log second call
    log_payload_2 = {
        "counsellor_name": "Pooja Sharma",
        "call_disposition": "INTERESTED_IN_BATCH",
        "notes": "Interested in PW GATE Dropper Batch for Rank Improvement. Follow-up discount offered.",
        "follow_up_date": "2026-11-25",
    }
    res_log2 = client.post(f"/api/v1/counsellor/students/{phone}/call-log", json=log_payload_2)
    assert res_log2.status_code == 200

    # 5. Verify student disposition updated to latest
    res_prof2 = client.get(f"/api/v1/counsellor/students/{phone}")
    assert res_prof2.status_code == 200
    prof2_data = res_prof2.json()
    assert prof2_data["call_disposition"] == "INTERESTED_IN_BATCH"
    assert prof2_data["last_contacted_at"] is not None
    assert len(prof2_data["call_history"]) == 2

    # 6. Verify chronological call history endpoint
    res_hist = client.get(f"/api/v1/counsellor/students/{phone}/call-history")
    assert res_hist.status_code == 200
    hist = res_hist.json()
    assert len(hist) == 2
    assert hist[0]["call_disposition"] == "INTERESTED_IN_BATCH"  # latest first
    assert hist[1]["call_disposition"] == "CONNECTED_FOLLOW_UP"


def test_telephony_click_to_call_links():
    phone = "9876500001"
    res = client.get(f"/api/v1/counsellor/students/{phone}/telephony-link")
    assert res.status_code == 200
    data = res.json()
    assert data["student_phone"] == phone
    assert data["tel_uri"] == "tel:+919876500001"
    assert "sip:919876500001@pw-telephony.local" in data["sip_uri"]
    assert "https://wa.me/919876500001" in data["wa_web_link"]
    assert "Rohan" in data["wa_web_link"]


def test_lead_summary_analytics():
    res = client.get("/api/v1/counsellor/analytics/lead-summary")
    assert res.status_code == 200
    data = res.json()
    assert data["total_submissions"] >= 1
    assert "INTERESTED_IN_BATCH" in data["disposition_counts"]
    assert data["avg_marks_lost_to_negatives"] >= 0.0


def test_export_leads_csv():
    res = client.get("/api/v1/counsellor/export/csv?paper_code=CS")
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    assert "attachment; filename=PW_GATE_Leads_" in res.headers["content-disposition"]
    csv_text = res.text
    assert "Student Name,Phone,Email" in csv_text
    assert "Rohan Mehra" in csv_text
    assert "9876500001" in csv_text
    assert "INTERESTED_IN_BATCH" in csv_text


def test_counsellor_contact_card_popup_replaces_tel_dialing():
    """
    Verifies that counsellor laptop workstation mode strictly forbids
    OS-level tel: call initiation and instead opens an interactive Contact Details Card
    with copy buttons and WhatsApp Web links.
    """
    # 1. Verify students list includes student_email for contact card
    res_students = client.get("/api/v1/counsellor/students?search=9876500001")
    assert res_students.status_code == 200
    data = res_students.json()
    assert data["total"] >= 1
    student = data["students"][0]
    assert "student_email" in student
    assert student["student_email"] == "rohan@example.com"

    # 2. Verify frontend index.html has zero tel: links and provides contact modal
    res_html = client.get("/")
    assert res_html.status_code == 200
    html_content = res_html.text

    # Must NOT contain tel: link or direct dial button
    assert 'href="tel:' not in html_content
    assert "modal-tel-btn" not in html_content
    assert "Dial Tel" not in html_content

    # Must contain contact card popup components
    assert "openContactModal" in html_content
    assert "modal-phone-display" in html_content
    assert "copyModalPhone" in html_content
    assert "Copy Number" in html_content
    assert "Laptop Workstation Mode:" in html_content
    assert "WhatsApp Web" in html_content
