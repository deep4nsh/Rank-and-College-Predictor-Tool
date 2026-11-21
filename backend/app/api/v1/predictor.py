from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from backend.app.core.knowledge_base import (
    get_branch_matrix,
    get_ccmt_cutoffs,
    get_coap_cutoffs,
    get_psu_cutoffs,
)
from backend.app.core.matcher import match_options_for_student
from backend.app.core.rank_spline import MonotonicRankEngine

router = APIRouter(prefix="/predictor", tags=["Predictor"])


@router.get("/quick-estimate")
def quick_estimate(
    score: float = Query(..., ge=0.0, le=100.0, description="Raw or normalized score"),
    paper_code: str = Query("CS", description="GATE paper code e.g. CS, ME, CE, EE"),
    category: str = Query("GEN", description="GEN, OBC_NCL, EWS, SC, ST"),
    btech_pct: float = Query(70.0, ge=40.0, le=100.0),
    age: int = Query(23, ge=18, le=45),
    has_ncl: bool = Query(True),
    include_interdisciplinary: bool = Query(True),
):
    """
    Provides instant rank, college (COAP/CCMT), and PSU predictions from a score
    with multi-year weighted moving average cutoffs.
    """
    spline = MonotonicRankEngine(paper_code)
    rank_pred = spline.predict_rank(score)

    coap_data = get_coap_cutoffs()
    ccmt_data = get_ccmt_cutoffs()
    psu_data = get_psu_cutoffs()
    branch_matrix = get_branch_matrix()

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
        include_cross_discipline=include_interdisciplinary,
        historical_coap_data=coap_data,
        historical_ccmt_data=ccmt_data,
        historical_psu_data=psu_data,
        branch_matrix_data=branch_matrix,
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
        "interdisciplinary_matches_count": len(summary.interdisciplinary_options),
        "coap_options": [o.__dict__ for o in summary.coap_options],
        "ccmt_options": [o.__dict__ for o in summary.ccmt_options],
        "psu_options": [o.__dict__ for o in summary.psu_options],
        "interdisciplinary_options": [o.__dict__ for o in summary.interdisciplinary_options],
    }


@router.get("/colleges")
def filter_colleges(
    gate_score: int = Query(..., ge=100, le=1000),
    paper_code: str = Query("CS"),
    category: str = Query("GEN"),
    counselling_body: Optional[str] = Query(None, description="COAP or CCMT"),
    tier: Optional[str] = Query(None, description="SAFE, TARGET, or AMBITIOUS"),
    offer_type: Optional[str] = Query(None, description="DIRECT_OFFER or INTERVIEW_CALL"),
    include_interdisciplinary: bool = Query(True),
):
    """
    Dedicated college prediction filter for counsellors.
    Allows filtering by counselling body (COAP/CCMT), tier, and offer type.
    """
    coap_data = get_coap_cutoffs()
    ccmt_data = get_ccmt_cutoffs()
    branch_matrix = get_branch_matrix()

    summary = match_options_for_student(
        gate_score=gate_score,
        predicted_air=500,
        paper_code=paper_code,
        category=category,
        include_cross_discipline=include_interdisciplinary,
        historical_coap_data=coap_data,
        historical_ccmt_data=ccmt_data,
        branch_matrix_data=branch_matrix,
    )

    all_colleges = []
    if counselling_body != "CCMT":
        all_colleges.extend(summary.coap_options)
    if counselling_body != "COAP":
        all_colleges.extend(summary.ccmt_options)

    if include_interdisciplinary:
        for opt in summary.interdisciplinary_options:
            if counselling_body and opt.counselling_body != counselling_body.upper():
                continue
            all_colleges.append(opt)

    # Apply tier filter
    if tier:
        all_colleges = [c for c in all_colleges if c.match_tier == tier.upper().strip()]

    # Apply offer_type filter
    if offer_type:
        all_colleges = [c for c in all_colleges if c.offer_type == offer_type.upper().strip()]

    return {
        "gate_score": gate_score,
        "paper_code": paper_code.upper(),
        "category": category.upper(),
        "total_results": len(all_colleges),
        "results": [c.__dict__ for c in all_colleges],
    }


@router.get("/psus")
def filter_psus(
    gate_score: int = Query(..., ge=100, le=1000),
    paper_code: str = Query("CS"),
    category: str = Query("GEN"),
    btech_pct: float = Query(70.0, ge=40.0, le=100.0),
    age: int = Query(23, ge=18, le=45),
    tier: Optional[str] = Query(None, description="SAFE, TARGET, or AMBITIOUS"),
    only_eligible: bool = Query(False, description="Exclude age/B.Tech % disqualified options"),
):
    """
    Dedicated PSU recruitment prediction filter for counsellors.
    Evaluates shortlist probability and applies strict eligibility rules.
    """
    psu_data = get_psu_cutoffs()

    summary = match_options_for_student(
        gate_score=gate_score,
        predicted_air=500,
        paper_code=paper_code,
        category=category,
        btech_percentage=btech_pct,
        candidate_age=age,
        historical_psu_data=psu_data,
    )

    results = summary.psu_options

    if only_eligible:
        results = [p for p in results if p.is_eligible]

    if tier:
        results = [p for p in results if p.match_tier == tier.upper().strip()]

    return {
        "gate_score": gate_score,
        "paper_code": paper_code.upper(),
        "category": category.upper(),
        "total_results": len(results),
        "results": [p.__dict__ for p in results],
    }


@router.get("/cross-discipline")
def get_cross_discipline_branches(paper_code: str = Query("ME")):
    """
    Returns all eligible M.Tech/MS interdisciplinary specializations for a qualifying GATE paper.
    """
    matrix = get_branch_matrix()
    clean = paper_code.upper().strip()
    specializations = matrix.get(clean, [])
    return {
        "paper_code": clean,
        "total_specializations": len(specializations),
        "eligible_specializations": specializations,
    }
