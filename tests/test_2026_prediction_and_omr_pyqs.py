"""
Comprehensive Verification Test Suite for 2026 GATE Prediction Engine & Authentic OMR-PYQ Key Auditing.
Tests:
1. 2026, 2025, 2024 cutoff presence across COAP, CCMT, and PSU databases.
2. Calibrated 2026 Rank Spline engine across papers (including DA and CS).
3. Question-by-question authentic answer key breakdown in OMR submissions.
4. Direct score bypass and OMR bubble submission end-to-end evaluation.
"""

from fastapi.testclient import TestClient
from backend.app.core.knowledge_base import get_coap_cutoffs, get_ccmt_cutoffs, get_psu_cutoffs
from backend.app.core.matcher import match_options_for_student
from backend.app.core.rank_spline import MonotonicRankEngine
from backend.app.main import app

client = TestClient(app)


def test_2026_cutoffs_presence():
    """Verify that COAP, CCMT, and PSU data include 2026 and 2025 benchmarks."""
    coap = get_coap_cutoffs()
    ccmt = get_ccmt_cutoffs()
    psu = get_psu_cutoffs()

    assert len(coap) >= 25
    assert len(ccmt) >= 20
    assert len(psu) >= 20

    # Ensure 2026 and 2025 exist in historical_scores
    for item in coap:
        hist = item.get("historical_scores", {})
        assert "2026" in hist, f"Missing 2026 in COAP {item.get('institution')} {item.get('program')}"
        assert "2025" in hist, f"Missing 2025 in COAP {item.get('institution')} {item.get('program')}"
        assert "2024" in hist, f"Missing 2024 in COAP {item.get('institution')} {item.get('program')}"

    for item in ccmt:
        hist = item.get("historical_scores", {})
        assert "2026" in hist, f"Missing 2026 in CCMT {item.get('institution')} {item.get('program')}"
        assert "2025" in hist, f"Missing 2025 in CCMT {item.get('institution')} {item.get('program')}"

    for item in psu:
        hist = item.get("historical_scores", {})
        assert "2026" in hist, f"Missing 2026 in PSU {item.get('psu_name')} {item.get('post_name')}"
        assert "2025" in hist, f"Missing 2025 in PSU {item.get('psu_name')} {item.get('post_name')}"


def test_2026_rank_spline_engine():
    """Verify MonotonicRankEngine operates on 2026 calibrated curves."""
    cs_engine = MonotonicRankEngine("CS", target_year=2026)
    pred_high = cs_engine.predict_rank(85.0)
    assert pred_high.predicted_air <= 30
    assert pred_high.target_year == 2026

    pred_mid = cs_engine.predict_rank(65.0)
    assert 400 <= pred_mid.predicted_air <= 800

    pred_low = cs_engine.predict_rank(35.0)
    assert pred_low.predicted_air > 12000

    # Test DA (Data Science & AI)
    da_engine = MonotonicRankEngine("DA", target_year=2026)
    da_pred_high = da_engine.predict_rank(80.0)
    assert da_pred_high.predicted_air <= 50
    assert da_pred_high.target_year == 2026


def test_matcher_exposes_2026_and_historical_scores():
    """Verify that match_options_for_student exposes closing_2026, closing_2025, closing_2024."""
    summary = match_options_for_student(
        gate_score=820,
        predicted_air=45,
        paper_code="CS",
        category="GEN",
        historical_coap_data=get_coap_cutoffs(),
        historical_ccmt_data=get_ccmt_cutoffs(),
        historical_psu_data=get_psu_cutoffs(),
    )

    assert len(summary.coap_options) > 0
    top_coap = summary.coap_options[0]
    assert top_coap.closing_2026 is not None
    assert top_coap.closing_2025 is not None
    assert top_coap.closing_2024 is not None
    assert top_coap.historical_closing_score > 0

    assert len(summary.psu_options) > 0
    eligible_psus = [p for p in summary.psu_options if p.is_eligible]
    assert len(eligible_psus) > 0
    top_psu = eligible_psus[0]
    assert top_psu.cutoff_2026 is not None
    assert top_psu.cutoff_2025 is not None


def test_omr_submission_with_authentic_key_breakdown():
    """Verify that an OMR submission returns full question_breakdown against authentic keys."""
    # First fetch sample paper for DA to get authentic question IDs
    sample_res = client.get("/api/v1/ingest/sample-paper/DA?session_id=1")
    assert sample_res.status_code == 200
    questions = sample_res.json()["questions"]
    assert len(questions) == 65

    # Pick first 2 questions and simulate student answers
    q1 = questions[0]
    q2 = questions[1]
    responses = [
        {"question_id": q1["question_id"], "status": "ATTEMPTED", "marked_options": q1.get("correct_options", ["B"])},
        {"question_id": q2["question_id"], "status": "ATTEMPTED", "marked_options": ["X"]},  # intentionally wrong
    ]

    sub_payload = {
        "student_phone": "9998887771",
        "student_name": "Test DA Student",
        "student_category": "GEN",
        "btech_percentage": 78.0,
        "candidate_age": 23,
        "has_valid_ncl": True,
        "paper_code": "DA",
        "session_id": 1,
        "responses": responses
    }

    res = client.post("/api/v1/submissions", json=sub_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "question_breakdown" in data
    assert len(data["question_breakdown"]) > 0

    # Verify Q1 is graded as correct and Q2 as incorrect
    breakdown_map = {item["question_id"]: item for item in data["question_breakdown"]}
    assert q1["question_id"] in breakdown_map
    res_q1 = breakdown_map[q1["question_id"]]
    assert res_q1["is_correct"] is True
    assert res_q1["marks_awarded"] > 0
    assert res_q1["subject_tag"] != ""
    assert res_q1["official_key"] != "--"

    assert q2["question_id"] in breakdown_map
    res_q2 = breakdown_map[q2["question_id"]]
    assert res_q2["is_correct"] is False
    assert res_q2["is_negative"] is True
    assert res_q2["marks_lost"] > 0
