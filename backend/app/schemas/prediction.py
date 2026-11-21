from typing import List, Optional
from pydantic import BaseModel


class CollegeOptionSchema(BaseModel):
    institution_name: str
    program_name: str
    counselling_body: str
    offer_type: str
    historical_closing_score: int
    match_tier: str
    probability_pct: int
    counsellor_note: str


class PSUOptionSchema(BaseModel):
    psu_name: str
    post_name: str
    min_gate_score: int
    min_btech_percentage: float
    max_age_general: int
    match_tier: str
    probability_pct: int
    is_eligible: bool
    eligibility_note: str


class StudentPredictionReportSchema(BaseModel):
    student_phone: str
    student_name: str
    paper_code: str
    session_id: int
    raw_score_total: float
    raw_score_aptitude: float
    raw_score_core: float
    marks_lost_to_negatives: float
    normalized_marks: float
    gate_score: int
    predicted_air: int
    air_range_min: int
    air_range_max: int
    lead_classification: str
    coap_options: List[CollegeOptionSchema]
    ccmt_options: List[CollegeOptionSchema]
    psu_options: List[PSUOptionSchema]
