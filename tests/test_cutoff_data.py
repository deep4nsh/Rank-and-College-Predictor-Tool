import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_branch_matrix_validity():
    p = DATA_DIR / "branch_matrix.json"
    assert p.exists()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "CS" in data
    assert "ME" in data
    assert "EE" in data
    assert "EC" in data
    assert "CE" in data
    assert "DA" in data
    assert len(data["CS"]) >= 5
    assert len(data["ME"]) >= 5


def test_cutoffs_coap_validity():
    p = DATA_DIR / "cutoffs_coap.json"
    assert p.exists()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) >= 15
    for item in data:
        assert "institution" in item
        assert "program" in item
        assert "paper_code" in item
        assert item["offer_type"] in ["DIRECT_OFFER", "INTERVIEW_CALL"]
        if "historical_scores" in item:
            for yr, cat_scores in item["historical_scores"].items():
                assert "GEN" in cat_scores
                assert 200 <= cat_scores["GEN"] <= 1000


def test_cutoffs_ccmt_validity():
    p = DATA_DIR / "cutoffs_ccmt.json"
    assert p.exists()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) >= 15
    for item in data:
        assert "institution" in item
        assert "program" in item
        assert "paper_code" in item
        assert "round" in item
        assert 200 <= item["cutoffs"]["GEN"] <= 1000


def test_cutoffs_psu_validity():
    p = DATA_DIR / "cutoffs_psu.json"
    assert p.exists()
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data) >= 10
    for item in data:
        assert "psu_name" in item
        assert "post_name" in item
        assert "min_btech_pct" in item
        assert item["min_btech_pct"] in [60.0, 65.0]
        assert "max_age_general" in item
        assert 24 <= item["max_age_general"] <= 30
        assert 300 <= item["cutoffs"]["GEN"] <= 1000
