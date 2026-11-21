from typing import List, Optional
from pydantic import BaseModel, Field


class ResponseItemSchema(BaseModel):
    question_id: str
    status: str = Field("ATTEMPTED", pattern="^(ATTEMPTED|SKIPPED)$")
    marked_options: Optional[List[str]] = None
    nat_value: Optional[str] = None


class StudentSubmissionCreateSchema(BaseModel):
    student_phone: str = Field(..., pattern=r"^[6-9]\d{9}$", description="10-digit Indian Mobile")
    student_name: str = Field(..., min_length=2, max_length=64)
    student_email: Optional[str] = None
    student_category: str = Field("GEN", pattern="^(GEN|OBC_NCL|OBC|EWS|SC|ST|PWD)$")
    btech_percentage: float = Field(70.0, ge=40.0, le=100.0)
    candidate_age: int = Field(22, ge=18, le=45)
    has_valid_ncl: bool = True
    pw_batch_id: Optional[str] = None
    paper_code: str
    session_id: int = Field(1, ge=1, le=4)
    responses: List[ResponseItemSchema]
