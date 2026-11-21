import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from backend.app.core.matcher import match_options_for_student
from backend.app.core.rank_spline import MonotonicRankEngine

router = APIRouter(prefix="/predictor", tags=["Predictor"])

DATA_DIR = Path(__file__).resolve().parents[4] / "data"

def load_json(filename: str):
    p = DATA_DIR / filename
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

@router.get("/quick-estimate")
def quick_estimate(
    score: float = Query(..., ge=0.0, le=100.0, description="Raw or normalized score"),
    paper_code: str = Query("CS", description="GATE paper code e.g. CS, ME, CE, EE"),
    category: str = Query("GEN", description="GEN, OBC, EWS, SC, ST"),
    btech_pct: float = Query(70.0, ge=40.0, le=100.0),
    age: int = Query(23, ge=18, le=45),
    has_ncl: bool = Query(True),
):
    """
    Provides instant rank, college (COAP/CCMT), and PSU predictions from a score.
    """
    spline = MonotonicRankEngine(paper_code)
    rank_pred = spline.predict_rank(score)

    coap_data = load_json("cutoffs_coap.json")
    ccmt_data = load_json("cutoffs_ccmt.json")
    psu_data = load_json("cutoffs_psu.json")

    # Proxy GATE score approximation
    approx_gate_score = min(1000, max(100, int(350 + (score - 28.5) * 11.5)))

    summary = match_options_for_student(
        gate_score=approx_gate_score,
        predicted_air=rank_pred.predicted_air,
        paper_code=paper_code,
        category=category,
        btech_percentage=btech_pct,
        candidate_age=age,
        has_valid_ncl=has_ncl,
        historical_coap_data=coap_data,
        historical_ccmt_data=ccmt_data,
        historical_psu_data=psu_data,
    )

    return {
        "paper_code": paper_code.upper(),
        "input_score": score,
        "approx_gate_score": approx_gate_score,
        "predicted_air": rank_pred.predicted_air,
        "air_range": f"{rank_pred.air_range_min} - {rank_pred.air_range_max}",
        "confidence": rank_pred.confidence_level,
        "lead_classification": summary.lead_classification,
        "coap_matches_count": len(summary.coap_options),
        "ccmt_matches_count": len(summary.ccmt_options),
        "psu_matches_count": len(summary.psu_options),
        "coap_options": [o.__dict__ for o in summary.coap_options],
        "ccmt_options": [o.__dict__ for o in summary.ccmt_options],
        "psu_options": [o.__dict__ for o in summary.psu_options],
    }
