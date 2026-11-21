"""
Three-Tier College & PSU Prediction Engine (COAP, CCMT, PSUs)
Categorizes options into AMBITIOUS, TARGET, and SAFE.
Distinguishes COAP Direct Admission vs Interview Calls.
Enforces hard eligibility disqualifiers (B.Tech %, Age, NCL certificate).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class CollegeOption:
    institution_name: str  # e.g., "IIT Bombay", "NIT Trichy"
    program_name: str  # e.g., "Computer Science and Engineering"
    counselling_body: str  # "COAP", "CCMT"
    offer_type: str  # "DIRECT_OFFER", "INTERVIEW_CALL"
    historical_closing_score: int
    match_tier: str  # "AMBITIOUS", "TARGET", "SAFE"
    probability_pct: int
    counsellor_note: str


@dataclass
class PSUOption:
    psu_name: str  # e.g., "IOCL", "ONGC", "NTPC", "BHEL"
    post_name: str  # e.g., "Graduate Apprentice Engineer (GAE)"
    min_gate_score: int
    min_btech_percentage: float
    max_age_general: int
    match_tier: str  # "AMBITIOUS", "TARGET", "SAFE"
    probability_pct: int
    is_eligible: bool
    eligibility_note: str


@dataclass
class CounsellingRecommendationSummary:
    student_gate_score: int
    predicted_air: int
    category: str
    target_paper: str
    lead_classification: str  # "SUPER_TOPPER", "PSU_AND_TOP_IIT", "NIT_PROSPECT", "NURTURE_REPEATER"
    coap_options: List[CollegeOption]
    ccmt_options: List[CollegeOption]
    psu_options: List[PSUOption]


def classify_lead_priority(gate_score: int, air: int) -> str:
    """
    Classifies student into operational counsellor priority bands.
    """
    if gate_score >= 820 or air <= 100:
        return "SUPER_TOPPER"
    elif gate_score >= 700 or air <= 500:
        return "PSU_AND_TOP_IIT"
    elif gate_score >= 550 or air <= 2500:
        return "NIT_PROSPECT"
    else:
        return "NURTURE_REPEATER"


def match_options_for_student(
    gate_score: int,
    predicted_air: int,
    paper_code: str,
    category: str = "GEN",
    btech_percentage: float = 70.0,
    candidate_age: int = 23,
    has_valid_ncl: bool = True,
    historical_coap_data: Optional[List[Dict]] = None,
    historical_ccmt_data: Optional[List[Dict]] = None,
    historical_psu_data: Optional[List[Dict]] = None,
) -> CounsellingRecommendationSummary:
    """
    Evaluates candidate GATE Score & Category against COAP, CCMT, and PSU databases.
    Categorizes into Safe, Target, and Ambitious tiers.
    """
    # Normalize category: If OBC without valid NCL, treat as GEN
    effective_cat = category.upper().strip()
    if effective_cat == "OBC" and not has_valid_ncl:
        effective_cat = "GEN"

    coap_matches: List[CollegeOption] = []
    ccmt_matches: List[CollegeOption] = []
    psu_matches: List[PSUOption] = []

    # 1. COAP Matcher (IITs / IISc)
    coap_records = historical_coap_data or []
    for item in coap_records:
        if item.get("paper_code", "").upper() != paper_code.upper():
            continue
        
        # Category specific cutoff score with fallback
        cutoff = item.get("cutoffs", {}).get(effective_cat, item.get("cutoffs", {}).get("GEN", 700))
        delta = gate_score - cutoff
        offer_type = item.get("offer_type", "DIRECT_OFFER")

        if delta >= 35:
            tier = "SAFE"
            prob = 90
            note = f"Score is +{delta} above historical closing score. High admission probability."
        elif -20 <= delta < 35:
            tier = "TARGET"
            prob = 65
            note = f"Score aligns closely ({'+' if delta >= 0 else ''}{delta}) with recent cutoff trends."
        elif -50 <= delta < -20:
            tier = "AMBITIOUS"
            prob = 30
            note = f"Opportunity in spot rounds or subsequent offer windows ({delta} below cutoff)."
        else:
            continue  # Out of range

        coap_matches.append(
            CollegeOption(
                institution_name=item.get("institution", "IIT"),
                program_name=item.get("program", "M.Tech"),
                counselling_body="COAP",
                offer_type=offer_type,
                historical_closing_score=cutoff,
                match_tier=tier,
                probability_pct=prob,
                counsellor_note=note,
            )
        )

    # 2. CCMT Matcher (NITs / IIITs / CFTIs)
    ccmt_records = historical_ccmt_data or []
    for item in ccmt_records:
        if item.get("paper_code", "").upper() != paper_code.upper():
            continue

        cutoff = item.get("cutoffs", {}).get(effective_cat, item.get("cutoffs", {}).get("GEN", 550))
        delta = gate_score - cutoff

        if delta >= 30:
            tier = "SAFE"
            prob = 92
            note = f"Strong safe option (+{delta} points above regular round closing score)."
        elif -15 <= delta < 30:
            tier = "TARGET"
            prob = 70
            note = f"Strong target for regular rounds 1-3 ({'+' if delta >= 0 else ''}{delta} points)."
        elif -45 <= delta < -15:
            tier = "AMBITIOUS"
            prob = 35
            note = f"Viable in National Spot Round (NSR) or Special Round 2 ({delta} points)."
        else:
            continue

        ccmt_matches.append(
            CollegeOption(
                institution_name=item.get("institution", "NIT"),
                program_name=item.get("program", "M.Tech"),
                counselling_body="CCMT",
                offer_type="DIRECT_OFFER",
                historical_closing_score=cutoff,
                match_tier=tier,
                probability_pct=prob,
                counsellor_note=note,
            )
        )

    # 3. PSU Recruitment Matcher
    psu_records = historical_psu_data or []
    for item in psu_records:
        if item.get("paper_code", "").upper() != paper_code.upper():
            continue

        cutoff = item.get("cutoffs", {}).get(effective_cat, item.get("cutoffs", {}).get("GEN", 750))
        min_pct = item.get("min_btech_pct", 65.0)
        max_age = item.get("max_age_general", 26)
        if effective_cat in ["OBC", "OBC_NCL"]:
            max_age += 3
        elif effective_cat in ["SC", "ST"]:
            max_age += 5

        delta = gate_score - cutoff

        # Hard criteria verification
        is_eligible = True
        notes = []
        if btech_percentage < min_pct:
            is_eligible = False
            notes.append(f"B.Tech percentage {btech_percentage}% is below required {min_pct}%.")
        if candidate_age > max_age:
            is_eligible = False
            notes.append(f"Age {candidate_age} exceeds max age limit of {max_age} years.")

        if delta >= 30:
            tier = "SAFE"
            prob = 85 if is_eligible else 0
        elif -15 <= delta < 30:
            tier = "TARGET"
            prob = 60 if is_eligible else 0
        elif -45 <= delta < -15:
            tier = "AMBITIOUS"
            prob = 25 if is_eligible else 0
        else:
            continue

        status_text = "Eligible for interview call." if is_eligible else "Disqualified: " + "; ".join(notes)

        psu_matches.append(
            PSUOption(
                psu_name=item.get("psu_name", "PSU"),
                post_name=item.get("post_name", "Graduate Engineer Trainee"),
                min_gate_score=cutoff,
                min_btech_percentage=min_pct,
                max_age_general=max_age,
                match_tier=tier,
                probability_pct=prob,
                is_eligible=is_eligible,
                eligibility_note=status_text,
            )
        )

    # Sort matches by tier (SAFE first, then TARGET, then AMBITIOUS) and score descending
    tier_order = {"SAFE": 1, "TARGET": 2, "AMBITIOUS": 3}
    coap_matches.sort(key=lambda x: (tier_order.get(x.match_tier, 4), -x.historical_closing_score))
    ccmt_matches.sort(key=lambda x: (tier_order.get(x.match_tier, 4), -x.historical_closing_score))
    psu_matches.sort(key=lambda x: (tier_order.get(x.match_tier, 4), -x.min_gate_score))

    lead_priority = classify_lead_priority(gate_score, predicted_air)

    return CounsellingRecommendationSummary(
        student_gate_score=gate_score,
        predicted_air=predicted_air,
        category=effective_cat,
        target_paper=paper_code.upper(),
        lead_classification=lead_priority,
        coap_options=coap_matches,
        ccmt_options=ccmt_matches,
        psu_options=psu_matches,
    )
