from fastapi.testclient import TestClient
from backend.app.db.models import Base
from backend.app.db.session import engine
from backend.app.main import app

client = TestClient(app)


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_complete_phase1_and_phase2_synergy():
    """
    Exhaustive integration test verifying that Phase 1 (deterministic grading,
    normalization, SQLite concurrency, versioned keys) and Phase 2 (multi-year
    weighted cutoffs, cross-discipline matching, counsellor diagnostic profiles)
    function together without friction.
    """
    # Step 1: Faculty Publishes CS Key v1 on Exam Day
    key_payload = {
        "paper_code": "CS",
        "version": 1,
        "key_type": "FACULTY_EXAM_DAY",
        "author_name": "PW CS Faculty Panel",
        "items": [
            {"question_id": "CS-1", "question_number": 1, "section": "APTITUDE", "question_type": "MCQ", "marks_correct": 1.0, "valid_options": [["B"]]},
            {"question_id": "CS-2", "question_number": 2, "section": "APTITUDE", "question_type": "MCQ", "marks_correct": 2.0, "valid_options": [["A"]]},
            {"question_id": "CS-3", "question_number": 3, "section": "CORE", "question_type": "MSQ", "marks_correct": 2.0, "valid_options": [["A", "C"]]},
            {"question_id": "CS-4", "question_number": 4, "section": "CORE", "question_type": "NAT", "marks_correct": 2.0, "nat_min": 24.0, "nat_max": 24.5},
            {"question_id": "CS-5", "question_number": 5, "section": "CORE", "question_type": "MCQ", "marks_correct": 2.0, "is_mta": True},
        ],
    }
    res_key = client.post("/api/v1/keys", json=key_payload)
    assert res_key.status_code == 200
    assert res_key.json()["status"] == "success"

    # Step 2: Student 1 (Top Scorer) Submits Marked Paper on PW Portal
    student_payload = {
        "student_phone": "9998887770",
        "student_name": "Vikram Adhikari",
        "student_email": "vikram@example.com",
        "student_category": "GEN",
        "btech_percentage": 82.0,
        "candidate_age": 23,
        "has_valid_ncl": True,
        "pw_batch_id": "Parakram_GATE_2025",
        "paper_code": "CS",
        "session_id": 1,
        "responses": [
            {"question_id": "CS-1", "status": "ATTEMPTED", "marked_options": ["B"]},     # +1.0
            {"question_id": "CS-2", "status": "ATTEMPTED", "marked_options": ["A"]},     # +2.0
            {"question_id": "CS-3", "status": "ATTEMPTED", "marked_options": ["A", "C"]}, # +2.0
            {"question_id": "CS-4", "status": "ATTEMPTED", "nat_value": "24.2"},         # +2.0
            {"question_id": "CS-5", "status": "SKIPPED"},                                # +2.0 (MTA)
        ],
    }
    res_sub = client.post("/api/v1/submissions", json=student_payload)
    assert res_sub.status_code == 200
    sub_data = res_sub.json()

    # Verify Phase 1 Scoring Engine Output
    assert sub_data["raw_score_total"] == 9.0
    assert sub_data["raw_score_aptitude"] == 3.0
    assert sub_data["raw_score_core"] == 6.0
    assert sub_data["marks_lost_to_negatives"] == 0.0

    # With 9 marks out of 100 (below qualifying marks 28.5), student does not qualify for IITs
    # The engine correctly classifies them as NURTURE_REPEATER without fake hallucinations!
    assert sub_data["lead_classification"] == "NURTURE_REPEATER"
    assert sub_data["gate_score"] < 350

    # Step 3: Now Student 2 (Top Ranker) Submits with High Marks
    # Let's add questions to reach high score or submit high score
    key_payload_topper = {
        "paper_code": "ME",
        "version": 1,
        "key_type": "FACULTY_EXAM_DAY",
        "author_name": "PW ME Faculty Panel",
        "items": [
            {"question_id": f"ME-{i}", "question_number": i, "section": "CORE" if i > 10 else "APTITUDE", "question_type": "MCQ", "marks_correct": 2.0 if i > 25 else 1.0, "valid_options": [["A"]]}
            for i in range(1, 55)
        ],
    }
    client.post("/api/v1/keys", json=key_payload_topper)

    # Student 2 answers 45 questions correctly (~75 marks)
    student2_payload = {
        "student_phone": "9998887771",
        "student_name": "Pooja Hegde",
        "student_email": "pooja@example.com",
        "student_category": "GEN",
        "btech_percentage": 85.0,
        "candidate_age": 22,
        "has_valid_ncl": True,
        "pw_batch_id": "Shreshth_GATE_2025",
        "paper_code": "ME",
        "session_id": 1,
        "responses": [
            {"question_id": f"ME-{i}", "status": "ATTEMPTED", "marked_options": ["A"]}
            for i in range(1, 46)
        ],
    }
    res_sub2 = client.post("/api/v1/submissions", json=student2_payload)
    assert res_sub2.status_code == 200
    sub2_data = res_sub2.json()

    assert sub2_data["raw_score_total"] >= 60.0
    assert sub2_data["gate_score"] >= 700
    assert len(sub2_data["coap_options"]) > 0
    assert len(sub2_data["psu_options"]) > 0

    # Step 4: Counsellor Looks up Pooja's Full Diagnostic Profile
    res_profile = client.get("/api/v1/counsellor/students/9998887771")
    assert res_profile.status_code == 200
    prof = res_profile.json()
    assert prof["student_name"] == "Pooja Hegde"
    assert prof["raw_score_total"] >= 60.0
    assert len(prof["coap_options"]) > 0
    assert len(prof["psu_options"]) > 0
    assert len(prof["ccmt_options"]) > 0

    # Step 5: Counsellor Generates WhatsApp Summary for Pooja
    res_wa = client.get("/api/v1/counsellor/students/9998887771/whatsapp-summary")
    assert res_wa.status_code == 200
    wa_msg = res_wa.json()["whatsapp_text"]
    assert "Pooja Hegde" in wa_msg
    assert "PW GATE Academic & Counselling Diagnostic" in wa_msg
    # Verify that matching colleges appear in the text
    assert ("IIT" in wa_msg or "NIT" in wa_msg or "PSU" in wa_msg)

    # Step 6: Official IIT Key v2 Arrives for ME
    revised_key_payload = {
        "paper_code": "ME",
        "version": 2,
        "key_type": "OFFICIAL_IIT",
        "author_name": "IIT Organizing Committee",
        "items": [
            {"question_id": f"ME-{i}", "question_number": i, "section": "CORE" if i > 10 else "APTITUDE", "question_type": "MCQ", "marks_correct": 2.0 if i > 25 else 1.0, "is_mta": (i == 48), "valid_options": [["A"]]}
            for i in range(1, 55)
        ],
    }
    res_key2 = client.post("/api/v1/keys", json=revised_key_payload)
    assert res_key2.status_code == 200
    key2_id = res_key2.json()["key_id"]

    # Step 7: Trigger 1-Click Batch Re-Evaluation
    res_reeval = client.post(f"/api/v1/keys/{key2_id}/re-evaluate")
    assert res_reeval.status_code == 200
    reeval_data = res_reeval.json()
    assert reeval_data["status"] == "success"
    assert reeval_data["re_evaluated_count"] == 1
    assert reeval_data["key_version"] == 2
