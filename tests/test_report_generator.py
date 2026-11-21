from backend.app.services.report_generator import generate_student_diagnostic_pdf


def test_generate_student_diagnostic_pdf_validity():
    student_info = {
        "name": "Tanmay Bhat",
        "phone": "9876543210",
        "category": "GEN",
        "paper_code": "CS",
        "batch": "PW Shreshth 2025",
        "has_valid_ncl": True,
    }

    eval_info = {
        "raw_score_total": 74.33,
        "raw_score_aptitude": 13.0,
        "raw_score_core": 61.33,
        "marks_lost_to_negatives": 1.66,
        "gate_score": 780,
        "predicted_air": 125,
        "air_range": "110 - 145",
        "lead_classification": "PSU_AND_TOP_IIT",
    }

    matches = {
        "coap_options": [
            {"institution_name": "IIT Bombay", "program_name": "Computer Science and Engineering", "match_tier": "SAFE", "admission_mode": "DIRECT_OFFER"},
            {"institution_name": "IIT Delhi", "program_name": "Computer Technology", "match_tier": "SAFE", "admission_mode": "DIRECT_OFFER"},
        ],
        "ccmt_options": [
            {"institution_name": "NIT Trichy", "program_name": "Computer Science and Engineering", "match_tier": "SAFE"},
        ],
        "psu_options": [
            {"psu_name": "IOCL", "post_name": "Graduate Engineer Trainee", "is_eligible": True, "eligibility_note": "Score well above shortlist cutoffs"},
        ],
    }

    buffer = generate_student_diagnostic_pdf(student_info, eval_info, matches)
    pdf_bytes = buffer.getvalue()

    # Verify standard PDF magic header and reasonable size (> 2000 bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 2000


def test_generate_pdf_with_special_xml_characters():
    """
    Edge case: Candidate name or batch containing &, <, >, or quotes
    must not break ReportLab XML paragraph parsing.
    """
    student_info = {
        "name": "Abhishek & Sons <PW Topper>",
        "phone": "9876543210",
        "category": "OBC & NCL",
        "paper_code": "CS",
        "batch": "PW R&D 'Special' Batch",
        "has_valid_ncl": True,
    }

    eval_info = {
        "raw_score_total": 60.0,
        "raw_score_aptitude": 10.0,
        "raw_score_core": 50.0,
        "marks_lost_to_negatives": 0.0,
        "gate_score": 680,
        "predicted_air": 450,
        "air_range": "400 - 500",
        "lead_classification": "NIT_PROSPECT",
    }

    matches = {
        "coap_options": [],
        "ccmt_options": [],
        "psu_options": [],
    }

    buffer = generate_student_diagnostic_pdf(student_info, eval_info, matches)
    pdf_bytes = buffer.getvalue()
    assert pdf_bytes.startswith(b"%PDF")
