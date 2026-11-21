"""
Three-Tier College & PSU Prediction Engine (COAP, CCMT, PSUs) - Phase 2
Features:
- Multi-Year Weighted Moving Average (0.50 * Y_2024 + 0.30 * Y_2023 + 0.20 * Y_2022)
- Interdisciplinary Cross-Discipline Branch Matching
- Categorizes options into AMBITIOUS, TARGET, and SAFE with fine-grained probability
- Distinguishes COAP Direct Admission vs Interview Calls
- Enforces hard eligibility disqualifiers (B.Tech %, Age, NCL certificate)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set


@dataclass
class CollegeOption:
    institution_name: str  # e.g., "IIT Bombay", "NIT Trichy"
    program_name: str  # e.g., "Computer Science and Engineering"
    counselling_body: str  # "COAP", "CCMT"
    offer_type: str  # "DIRECT_OFFER", "INTERVIEW_CALL"
    historical_closing_score: int
    match_tier: str  # "AMBITIOUS", "TARGET", "SAFE"
    probability_pct: int
    is_interdisciplinary: bool
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
    interdisciplinary_options: List[CollegeOption]


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


def get_cat_score_from_dict(d: Dict, cat: str) -> Optional[int]:
    """
    Extracts category cutoff score with proper PwD horizontal reservation handling.
    PwD cutoff falls back to SC/ST or 0.65 * GEN (never to raw GEN).
    """
    if not d:
        return None
    if cat in ["PWD", "GEN_PWD", "OBC_PWD", "SC_PWD", "ST_PWD"]:
        if "PWD" in d:
            return d["PWD"]
        if "SC" in d:
            return d["SC"]
        if "ST" in d:
            return d["ST"]
        if "GEN" in d:
            return int(round(d["GEN"] * 0.65))
        return None
    return d.get(cat, d.get("GEN"))


def compute_weighted_cutoff(item: Dict, category: str) -> int:
    """
    Calculates weighted moving average of previous years' cutoffs:
    0.50 * Y_latest + 0.30 * Y_prev + 0.20 * Y_old.
    Falls back gracefully if fewer years are recorded.
    """
    hist = item.get("historical_scores")
    cat = category.upper()
    if hist and isinstance(hist, dict):
        sorted_years = sorted(hist.keys(), reverse=True)
        scores = []
        for y in sorted_years:
            yr_dict = hist[y]
            val = get_cat_score_from_dict(yr_dict, cat)
            if val is not None:
                scores.append(val)

        if len(scores) >= 3:
            weighted = 0.50 * scores[0] + 0.30 * scores[1] + 0.20 * scores[2]
            return int(round(weighted))
        elif len(scores) == 2:
            weighted = 0.60 * scores[0] + 0.40 * scores[1]
            return int(round(weighted))
        elif len(scores) == 1:
            return int(scores[0])

    # Fallback to single cutoffs mapping
    cutoffs = item.get("cutoffs", {})
    val = get_cat_score_from_dict(cutoffs, cat)
    return int(val if val is not None else 650)


def match_options_for_student(
    gate_score: int,
    predicted_air: int,
    paper_code: str,
    category: str = "GEN",
    btech_percentage: float = 70.0,
    candidate_age: int = 23,
    has_valid_ncl: bool = True,
    include_cross_discipline: bool = True,
    historical_coap_data: Optional[List[Dict]] = None,
    historical_ccmt_data: Optional[List[Dict]] = None,
    historical_psu_data: Optional[List[Dict]] = None,
    branch_matrix_data: Optional[Dict[str, List[str]]] = None,
) -> CounsellingRecommendationSummary:
    """
    Evaluates candidate GATE Score & Category against multi-year COAP, CCMT, and PSU databases.
    Categorizes into Safe, Target, and Ambitious tiers with weighted moving average cutoffs.
    """
    clean_paper = paper_code.upper().strip()

    # Normalize category: If OBC without valid NCL certificate, treat as GEN
    effective_cat = category.upper().strip()
    if effective_cat in ["OBC", "OBC_NCL"] and not has_valid_ncl:
        effective_cat = "GEN"

    coap_matches: List[CollegeOption] = []
    ccmt_matches: List[CollegeOption] = []
    psu_matches: List[PSUOption] = []
    interdisciplinary_matches: List[CollegeOption] = []
    seen_college_keys: Set[tuple] = set()

    # Get permissible interdisciplinary program keywords
    eligible_specializations: Set[str] = set()
    if branch_matrix_data and clean_paper in branch_matrix_data:
        eligible_specializations = {s.lower() for s in branch_matrix_data[clean_paper]}

    # 1. COAP Matcher (IITs / IISc)
    coap_records = historical_coap_data or []
    for item in coap_records:
        item_paper = item.get("paper_code", "").upper().strip()
        item_program = item.get("program", "")
        offer_type = item.get("offer_type", "DIRECT_OFFER")

        # Check core match vs interdisciplinary match
        is_core = (item_paper == clean_paper)
        is_interdisc = False

        if not is_core and include_cross_discipline and eligible_specializations:
            # Check if any eligible specialization matches the program
            is_interdisc = any(spec in item_program.lower() for spec in eligible_specializations)

        if not is_core and not is_interdisc:
            continue

        weighted_cutoff = compute_weighted_cutoff(item, effective_cat)
        delta = gate_score - weighted_cutoff

        if delta >= 30:
            tier = "SAFE"
            prob = min(98, 85 + int(delta * 0.2))
            note = f"Score (+{delta}) comfortably above multi-year predicted cutoff ({weighted_cutoff}). High admission probability."
        elif -20 <= delta < 30:
            tier = "TARGET"
            prob = max(50, min(84, 65 + int(delta * 0.4)))
            note = f"Score aligns closely ({'+' if delta >= 0 else ''}{delta}) with 3-year weighted cutoff ({weighted_cutoff})."
        elif -55 <= delta < -20:
            tier = "AMBITIOUS"
            prob = max(15, min(45, 30 + int(delta * 0.3)))
            note = f"Opportunity in Round 4/5 or spot offer windows ({delta} points from {weighted_cutoff})."
        else:
            continue

        if is_interdisc:
            note = f"[Cross-Discipline] {note}"

        opt = CollegeOption(
            institution_name=item.get("institution", "IIT"),
            program_name=item_program,
            counselling_body="COAP",
            offer_type=offer_type,
            historical_closing_score=weighted_cutoff,
            match_tier=tier,
            probability_pct=prob,
            is_interdisciplinary=is_interdisc,
            counsellor_note=note,
        )

        ckey = (opt.institution_name, opt.program_name, opt.counselling_body, opt.offer_type)
        if ckey in seen_college_keys:
            continue
        seen_college_keys.add(ckey)

        if is_interdisc:
            interdisciplinary_matches.append(opt)
        else:
            coap_matches.append(opt)

    # 2. CCMT Matcher (NITs / IIITs / CFTIs)
    ccmt_records = historical_ccmt_data or []
    for item in ccmt_records:
        item_paper = item.get("paper_code", "").upper().strip()
        item_program = item.get("program", "")

        is_core = (item_paper == clean_paper)
        is_interdisc = False

        if not is_core and include_cross_discipline and eligible_specializations:
            is_interdisc = any(spec in item_program.lower() for spec in eligible_specializations)

        if not is_core and not is_interdisc:
            continue

        weighted_cutoff = compute_weighted_cutoff(item, effective_cat)
        delta = gate_score - weighted_cutoff

        if delta >= 30:
            tier = "SAFE"
            prob = min(98, 88 + int(delta * 0.2))
            note = f"Strong safe option (+{delta} points above 3-year weighted cutoff: {weighted_cutoff})."
        elif -15 <= delta < 30:
            tier = "TARGET"
            prob = max(50, min(85, 70 + int(delta * 0.4)))
            note = f"Strong target for regular rounds 1-3 ({'+' if delta >= 0 else ''}{delta} points from {weighted_cutoff})."
        elif -50 <= delta < -15:
            tier = "AMBITIOUS"
            prob = max(20, min(45, 35 + int(delta * 0.3)))
            note = f"Viable in National Spot Round (NSR) or Special Round 2 ({delta} points from {weighted_cutoff})."
        else:
            continue

        if is_interdisc:
            note = f"[Cross-Discipline] {note}"

        opt = CollegeOption(
            institution_name=item.get("institution", "NIT"),
            program_name=item_program,
            counselling_body="CCMT",
            offer_type="DIRECT_OFFER",
            historical_closing_score=weighted_cutoff,
            match_tier=tier,
            probability_pct=prob,
            is_interdisciplinary=is_interdisc,
            counsellor_note=note,
        )

        ckey = (opt.institution_name, opt.program_name, opt.counselling_body, opt.offer_type)
        if ckey in seen_college_keys:
            continue
        seen_college_keys.add(ckey)

        if is_interdisc:
            interdisciplinary_matches.append(opt)
        else:
            ccmt_matches.append(opt)

    # 3. PSU Recruitment Matcher
    psu_records = historical_psu_data or []
    for item in psu_records:
        if item.get("paper_code", "").upper().strip() != clean_paper:
            continue

        weighted_cutoff = compute_weighted_cutoff(item, effective_cat)
        min_pct = item.get("min_btech_pct", 65.0)
        max_age = item.get("max_age_general", 26)
        if effective_cat in ["OBC", "OBC_NCL"]:
            max_age += 3
        elif effective_cat in ["SC", "ST"]:
            max_age += 5
        elif effective_cat in ["PWD", "GEN_PWD", "OBC_PWD", "SC_PWD", "ST_PWD"]:
            max_age += 10

        delta = gate_score - weighted_cutoff

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
            prob = 88 if is_eligible else 0
        elif -15 <= delta < 30:
            tier = "TARGET"
            prob = 62 if is_eligible else 0
        elif -45 <= delta < -15:
            tier = "AMBITIOUS"
            prob = 28 if is_eligible else 0
        else:
            continue

        status_text = "Eligible for interview call shortlist." if is_eligible else "Disqualified: " + "; ".join(notes)

        psu_matches.append(
            PSUOption(
                psu_name=item.get("psu_name", "PSU"),
                post_name=item.get("post_name", "Graduate Engineer Trainee"),
                min_gate_score=weighted_cutoff,
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
    interdisciplinary_matches.sort(key=lambda x: (tier_order.get(x.match_tier, 4), -x.historical_closing_score))
    psu_matches.sort(key=lambda x: (tier_order.get(x.match_tier, 4), -x.min_gate_score))

    lead_priority = classify_lead_priority(gate_score, predicted_air)

    return CounsellingRecommendationSummary(
        student_gate_score=gate_score,
        predicted_air=predicted_air,
        category=effective_cat,
        target_paper=clean_paper,
        lead_classification=lead_priority,
        coap_options=coap_matches,
        ccmt_options=ccmt_matches,
        psu_options=psu_matches,
        interdisciplinary_options=interdisciplinary_matches,
    )
