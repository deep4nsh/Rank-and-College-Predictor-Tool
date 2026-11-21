from backend.app.core.matcher import match_options_for_student


MOCK_COAP = [
    {
        "institution": "IIT Bombay",
        "program": "Computer Science & Engineering",
        "paper_code": "CS",
        "offer_type": "DIRECT_OFFER",
        "cutoffs": {"GEN": 775, "OBC_NCL": 700, "SC": 500},
    },
    {
        "institution": "IIT Delhi",
        "program": "Computer Technology",
        "paper_code": "CS",
        "offer_type": "DIRECT_OFFER",
        "cutoffs": {"GEN": 760, "OBC_NCL": 685, "SC": 490},
    },
    {
        "institution": "IIT Roorkee",
        "program": "Computer Science & Engineering",
        "paper_code": "CS",
        "offer_type": "DIRECT_OFFER",
        "cutoffs": {"GEN": 710, "OBC_NCL": 640, "SC": 450},
    },
]

MOCK_CCMT = [
    {
        "institution": "NIT Trichy",
        "program": "Computer Science & Engineering",
        "paper_code": "CS",
        "cutoffs": {"GEN": 680, "OBC_NCL": 615, "SC": 430},
    },
    {
        "institution": "NIT Calicut",
        "program": "Computer Science & Engineering",
        "paper_code": "CS",
        "cutoffs": {"GEN": 590, "OBC_NCL": 530, "SC": 360},
    },
]

MOCK_PSU = [
    {
        "psu_name": "IOCL",
        "post_name": "Graduate Apprentice Engineer",
        "paper_code": "CS",
        "min_btech_pct": 65.0,
        "max_age_general": 26,
        "cutoffs": {"GEN": 760, "OBC_NCL": 690, "SC": 500},
    }
]


def test_high_scorer_recommendations():
    # Score 780, AIR 75 -> Super topper / PSU & Top IIT
    summary = match_options_for_student(
        gate_score=780,
        predicted_air=75,
        paper_code="CS",
        category="GEN",
        btech_percentage=75.0,
        candidate_age=23,
        historical_coap_data=MOCK_COAP,
        historical_ccmt_data=MOCK_CCMT,
        historical_psu_data=MOCK_PSU,
    )

    assert summary.lead_classification == "SUPER_TOPPER"
    assert len(summary.coap_options) >= 2
    # IIT Roorkee (cutoff 710) should be SAFE (780 - 710 = +70)
    roorkee = next(o for o in summary.coap_options if o.institution_name == "IIT Roorkee")
    assert roorkee.match_tier == "SAFE"

    # IOCL (cutoff 760) should be TARGET or SAFE and eligible
    iocl = summary.psu_options[0]
    assert iocl.is_eligible is True
    assert iocl.probability_pct > 50


def test_psu_disqualification_rules():
    # Student has 800 score, but is 30 years old (exceeds max age 26 for GEN)
    summary = match_options_for_student(
        gate_score=800,
        predicted_air=40,
        paper_code="CS",
        category="GEN",
        btech_percentage=60.0,  # Below IOCL 65% requirement
        candidate_age=30,  # Above IOCL 26 max age
        historical_coap_data=MOCK_COAP,
        historical_ccmt_data=MOCK_CCMT,
        historical_psu_data=MOCK_PSU,
    )

    iocl = summary.psu_options[0]
    assert iocl.is_eligible is False
    assert iocl.probability_pct == 0
    assert "below required" in iocl.eligibility_note
    assert "exceeds max age" in iocl.eligibility_note


def test_obc_without_ncl_fallback():
    # Student claims OBC but does not hold active NCL -> Must evaluate against GEN cutoff
    summary = match_options_for_student(
        gate_score=710,
        predicted_air=250,
        paper_code="CS",
        category="OBC",
        has_valid_ncl=False,  # Creamy layer
        historical_coap_data=MOCK_COAP,
        historical_ccmt_data=MOCK_CCMT,
        historical_psu_data=MOCK_PSU,
    )

    assert summary.category == "GEN"
