from fastapi.testclient import TestClient
from backend.app.core.matcher import compute_weighted_cutoff, match_options_for_student
from backend.app.main import app

client = TestClient(app)


def test_weighted_moving_average_cutoff():
    # 3-year record: 2024=775, 2023=765, 2022=780
    # Expected: 0.50*775 + 0.30*765 + 0.20*780 = 387.5 + 229.5 + 156.0 = 773
    mock_item = {
        "historical_scores": {
            "2024": {"GEN": 775, "OBC_NCL": 700},
            "2023": {"GEN": 765, "OBC_NCL": 690},
            "2022": {"GEN": 780, "OBC_NCL": 705},
        }
    }
    weighted_gen = compute_weighted_cutoff(mock_item, "GEN")
    assert weighted_gen == 773

    weighted_obc = compute_weighted_cutoff(mock_item, "OBC_NCL")
    # Expected: 0.50*700 + 0.30*690 + 0.20*705 = 350 + 207 + 141 = 698
    assert weighted_obc == 698


def test_interdisciplinary_cross_branch_matching():
    # A Mechanical student eligible for Robotics / AI / Energy Systems
    mock_branch_matrix = {
        "ME": ["Robotics & Automation", "Materials Science", "Energy Systems"]
    }
    mock_coap = [
        {
            "institution": "IIT Bombay",
            "program": "Thermal & Fluids Engineering",
            "paper_code": "ME",
            "offer_type": "DIRECT_OFFER",
            "cutoffs": {"GEN": 750},
        },
        {
            "institution": "IIT Hyderabad",
            "program": "Robotics & Automation",
            "paper_code": "INTERDISCIPLINARY",
            "offer_type": "INTERVIEW_CALL",
            "cutoffs": {"GEN": 680},
        },
    ]

    summary = match_options_for_student(
        gate_score=720,
        predicted_air=250,
        paper_code="ME",
        category="GEN",
        include_cross_discipline=True,
        historical_coap_data=mock_coap,
        branch_matrix_data=mock_branch_matrix,
    )

    # Core match: IIT Bombay Thermal
    assert len(summary.coap_options) == 1
    assert summary.coap_options[0].institution_name == "IIT Bombay"

    # Interdisciplinary match: IIT Hyderabad Robotics
    assert len(summary.interdisciplinary_options) == 1
    interdisc = summary.interdisciplinary_options[0]
    assert interdisc.institution_name == "IIT Hyderabad"
    assert interdisc.is_interdisciplinary is True
    assert "[Cross-Discipline]" in interdisc.counsellor_note


def test_colleges_filter_api():
    res = client.get("/api/v1/predictor/colleges?gate_score=760&paper_code=CS&counselling_body=COAP&tier=TARGET")
    assert res.status_code == 200
    data = res.json()
    assert data["gate_score"] == 760
    assert data["total_results"] >= 1
    for item in data["results"]:
        assert item["counselling_body"] == "COAP"
        assert item["match_tier"] == "TARGET"


def test_psu_filter_api():
    # Score 765 in ME
    res = client.get("/api/v1/predictor/psus?gate_score=765&paper_code=ME&category=GEN&btech_pct=72.0&age=24&only_eligible=true")
    assert res.status_code == 200
    data = res.json()
    assert data["total_results"] >= 1
    for psu in data["results"]:
        assert psu["is_eligible"] is True


def test_cross_discipline_api():
    res = client.get("/api/v1/predictor/cross-discipline?paper_code=CS")
    assert res.status_code == 200
    data = res.json()
    assert data["paper_code"] == "CS"
    assert "Artificial Intelligence" in data["eligible_specializations"]
