"""
Pydantic Schemas for Counsellor Operations:
Call logging, disposition tracking, lead filtering, and real-time operational analytics.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CallLogCreateSchema(BaseModel):
    counsellor_name: str = Field("PW Counsellor", min_length=2, max_length=64)
    call_disposition: str = Field(
        ...,
        pattern="^(INTERESTED_IN_BATCH|COAP_COUNSELLING_BOOKED|PSU_GDPI_BOOKED|CONNECTED_FOLLOW_UP|NOT_REACHABLE|WRONG_NUMBER|NOT_INTERESTED)$",
    )
    notes: Optional[str] = Field(None, max_length=1000)
    follow_up_date: Optional[str] = Field(None, description="ISO Date string YYYY-MM-DD")


class CallLogResponseSchema(BaseModel):
    log_id: str
    submission_id: str
    student_phone: str
    counsellor_name: str
    call_disposition: str
    notes: Optional[str]
    follow_up_date: Optional[str]
    logged_at: str


class LeadSummaryAnalyticsSchema(BaseModel):
    total_submissions: int
    super_topper_count: int
    psu_and_top_iit_count: int
    nit_prospect_count: int
    nurture_repeater_count: int
    disposition_counts: Dict[str, int]
    high_negative_marks_count: int
    avg_marks_lost_to_negatives: float
