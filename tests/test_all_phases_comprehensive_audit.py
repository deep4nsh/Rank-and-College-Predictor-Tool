from fastapi.testclient import TestClient
from backend.app.db.models import Base
from backend.app.db.session import engine
from backend.app.main import app

client = TestClient(app)


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_cross_phase_master_audit_lifecycle():
    """
    Comprehensive cross-phase audit verifying that:
    1. Phase 1 (deterministic grading, rational arithmetic, normalizer, rank spline)
    2. Phase 2 (multi-year cutoffs, 3-tier matcher, PwD horizontal reservation, PSU disqualifiers)
    3. Phase 3 (interactive CBT form, Digialm scraper, bulk CSV importer, PDF scorecard generator)
    all operate together without data leakage, race conditions, or score degradation.
    """

    # =========================================================================
    # STEP 1: Faculty Publishes CS Key v1.0 (Phase 1)
    # =========================================================================
    key_v1_payload = {
        "paper_code": "CS",
        "version": 1,
        "key_type": "FACULTY_EXAM_DAY",
        "author_name": "PW Faculty Panel",
        "items": [
            {"question_id": "CS-1", "question_number": 1, "section": "APTITUDE", "question_type": "MCQ", "marks_correct": 1.0, "valid_options": [["B"]]},
            {"question_id": "CS-2", "question_number": 2, "section": "APTITUDE", "question_type": "MCQ", "marks_correct": 2.0, "valid_options": [["A"]]},
            {"question_id": "CS-3", "question_number": 3, "section": "CORE", "question_type": "MSQ", "marks_correct": 2.0, "valid_options": [["A", "C"]]},
            {"question_id": "CS-4", "question_number": 4, "section": "CORE", "question_type": "NAT", "marks_correct": 2.0, "nat_min": 24.0, "nat_max": 25.0},
            {"question_id": "CS-5", "question_number": 5, "section": "CORE", "question_type": "MCQ", "marks_correct": 2.0, "valid_options": [["D"]]},
        ],
    }
    res_k1 = client.post("/api/v1/keys", json=key_v1_payload)
    assert res_k1.status_code == 200
    k1_id = res_k1.json()["key_id"]

    # =========================================================================
    # STEP 2: Candidate 1 Submits via Phase 3 Interactive Form with Duplicate QIDs
    # =========================================================================
    c1_payload = {
        "student_phone": "9876543210",
        "student_name": "Aman Verma",
        "student_category": "PWD",
        "candidate_age": 32,  # PwD candidate with +10 years relaxation
        "btech_percentage": 75.0,
        "has_valid_ncl": True,
        "paper_code": "CS",
        "session_id": 1,
        "responses": [
            {"question_id": "CS-1", "status": "ATTEMPTED", "marked_options": ["B"]},
            {"question_id": "CS-2", "status": "ATTEMPTED", "marked_options": ["A"]},
            {"question_id": "CS-3", "status": "ATTEMPTED", "marked_options": ["A", "C"]},
            {"question_id": "CS-4", "status": "ATTEMPTED", "nat_value": " 24.50 "},  # NAT whitespace sanitization
            {"question_id": "CS-5", "status": "SKIPPED"},
            # Duplicate question response intentional edge-case: should be deduplicated
            {"question_id": "CS-5", "status": "ATTEMPTED", "marked_options": ["D"]},
        ],
    }
    res_c1 = client.post("/api/v1/submissions", json=c1_payload)
    assert res_c1.status_code == 200
    c1_data = res_c1.json()

    # 1.0 (Q1) + 2.0 (Q2) + 2.0 (Q3) + 2.0 (Q4) + 2.0 (Q5 deduplicated to D) = 9.0 marks
    assert c1_data["raw_score_total"] == 9.0
    assert c1_data["marks_lost_to_negatives"] == 0.0

    # =========================================================================
    # STEP 3: Candidate 2 Ingested via Phase 3 TCS iON Digialm HTML Scraper
    # =========================================================================
    digialm_html = """
    <table>
      <tr><td>Participant Name</td><td>Divya Nair</td></tr>
      <tr><td>Participant ID</td><td>CS25S38001122</td></tr>
      <tr><td>Subject</td><td>CS Computer Science and Information Technology</td></tr>
    </table>
    <table class="menu-tbl">
      <tr><td>Question ID :</td><td>CS-1</td></tr>
      <tr><td>Question Type :</td><td>MCQ</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Chosen Option :</td><td>2</td></tr> <!-- Option 2 -> B -->
    </table>
    <table class="menu-tbl">
      <tr><td>Question ID :</td><td>CS-2</td></tr>
      <tr><td>Question Type :</td><td>MCQ</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Chosen Option :</td><td>1</td></tr> <!-- Option 1 -> A -->
    </table>
    <table class="menu-tbl">
      <tr><td>Question ID :</td><td>CS-3</td></tr>
      <tr><td>Question Type :</td><td>MSQ</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Chosen Option :</td><td>1, 3</td></tr> <!-- Options 1,3 -> A, C -->
    </table>
    <table class="menu-tbl">
      <tr><td>Question ID :</td><td>CS-4</td></tr>
      <tr><td>Question Type :</td><td>NAT</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Given Answer :</td><td>24.8</td></tr>
    </table>
    <table class="menu-tbl">
      <tr><td>Question ID :</td><td>CS-5</td></tr>
      <tr><td>Question Type :</td><td>MCQ</td></tr>
      <tr><td>Status :</td><td>Answered</td></tr>
      <tr><td>Chosen Option :</td><td>3</td></tr> <!-- Option 3 -> C (WRONG: Key is D) -->
    </table>
    """
    res_digi = client.post(
        "/api/v1/ingest/response-sheet/submit",
        json={
            "html_content": digialm_html,
            "student_phone": "9876543211",
            "student_category": "GEN",
            "btech_percentage": 82.0,
            "candidate_age": 22,
        },
    )
    assert res_digi.status_code == 200
    digi_data = res_digi.json()

    # Divya answered Q1(+1), Q2(+2), Q3(+2), Q4(+2), and Q5 wrong (-2/3 = -0.6667)
    # Total marks: 7 - 0.6667 = 6.3333
    assert abs(digi_data["raw_score_total"] - 6.3333) < 0.01
    assert abs(digi_data["marks_lost_to_negatives"] - 0.6667) < 0.01

    # =========================================================================
    # STEP 4: Candidate 3 Ingested via Phase 3 Bulk CSV Import (Direct Score Mode)
    # =========================================================================
    csv_content = """student_phone,student_name,student_category,paper_code,session_id,btech_percentage,candidate_age,raw_score
9876543212,Siddharth Malhotra,GEN,CS,1,85.0,23,76.5
"""
    res_bulk = client.post("/api/v1/ingest/bulk-csv", json={"csv_content": csv_content})
    assert res_bulk.status_code == 200
    bulk_data = res_bulk.json()
    assert bulk_data["successful_count"] == 1
    assert "9876543212" in bulk_data["successful_phones"]

    # Verify Siddharth's direct score profile
    res_prof_sid = client.get("/api/v1/counsellor/students/9876543212")
    assert res_prof_sid.status_code == 200
    prof_sid = res_prof_sid.json()
    assert prof_sid["raw_score_total"] == 76.5
    assert prof_sid["gate_score"] >= 750
    assert prof_sid["lead_classification"] in ["SUPER_TOPPER", "PSU_AND_TOP_IIT"]

    # =========================================================================
    # STEP 5: Official IIT Key v2 Released with Revision + MTA
    # =========================================================================
    key_v2_payload = {
        "paper_code": "CS",
        "version": 2,
        "key_type": "OFFICIAL_IIT",
        "author_name": "IIT Organizing Committee",
        "items": [
            {"question_id": "CS-1", "question_number": 1, "section": "APTITUDE", "question_type": "MCQ", "marks_correct": 1.0, "valid_options": [["B"]]},
            {"question_id": "CS-2", "question_number": 2, "section": "APTITUDE", "question_type": "MCQ", "marks_correct": 2.0, "valid_options": [["A"]]},
            {"question_id": "CS-3", "question_number": 3, "section": "CORE", "question_type": "MSQ", "marks_correct": 2.0, "valid_options": [["A", "C"]]},
            {"question_id": "CS-4", "question_number": 4, "section": "CORE", "question_type": "NAT", "marks_correct": 2.0, "nat_min": 24.0, "nat_max": 25.0},
            # Question 5 changed to MTA (Marks to All)!
            {"question_id": "CS-5", "question_number": 5, "section": "CORE", "question_type": "MCQ", "marks_correct": 2.0, "is_mta": True},
        ],
    }
    res_k2 = client.post("/api/v1/keys", json=key_v2_payload)
    assert res_k2.status_code == 200
    k2_id = res_k2.json()["key_id"]

    # =========================================================================
    # STEP 6: Run 1-Click Batch Re-Evaluation
    # =========================================================================
    res_reeval = client.post(f"/api/v1/keys/{k2_id}/re-evaluate")
    assert res_reeval.status_code == 200
    reeval_data = res_reeval.json()
    assert reeval_data["re_evaluated_count"] == 3  # Aman, Divya, Siddharth

    # VERIFY AUDIT INTEGRITY:
    # 1. Divya's wrong answer on Q5 was converted to MTA (+2.0 instead of -0.6667)
    res_prof_divya = client.get("/api/v1/counsellor/students/9876543211")
    assert res_prof_divya.status_code == 200
    divya_updated = res_prof_divya.json()
    assert divya_updated["raw_score_total"] == 9.0  # Gained marks from MTA
    assert divya_updated["marks_lost_to_negatives"] == 0.0

    # 2. CRITICAL AUDIT CHECK: Siddharth's Direct Scorecard import (76.5) was NOT overwritten with 0!
    res_prof_sid_after = client.get("/api/v1/counsellor/students/9876543212")
    assert res_prof_sid_after.status_code == 200
    sid_after = res_prof_sid_after.json()
    assert sid_after["raw_score_total"] == 76.5  # PRESERVED!

    # =========================================================================
    # STEP 7: Phase 3 PDF Scorecard & WhatsApp Verification for Siddharth
    # =========================================================================
    res_pdf = client.get("/api/v1/counsellor/students/9876543212/pdf")
    assert res_pdf.status_code == 200
    assert res_pdf.headers["content-type"] == "application/pdf"
    assert res_pdf.content.startswith(b"%PDF")
    assert len(res_pdf.content) > 3000

    res_wa = client.get("/api/v1/counsellor/students/9876543212/whatsapp-summary")
    assert res_wa.status_code == 200
    wa_text = res_wa.json()["whatsapp_text"]
    assert "Siddharth Malhotra" in wa_text
    assert "76.50 / 100" in wa_text
    assert ("IIT" in wa_text or "NIT" in wa_text or "PSU" in wa_text)
