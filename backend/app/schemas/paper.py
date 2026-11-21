from typing import List, Optional
from pydantic import BaseModel, Field


class QuestionSchema(BaseModel):
    question_number: int = Field(..., ge=1, le=65)
    section: str = Field(..., pattern="^(APTITUDE|CORE)$")
    question_type: str = Field(..., pattern="^(MCQ|MSQ|NAT)$")
    marks_correct: float = Field(..., ge=1.0, le=2.0)
    marks_negative: float = Field(0.0, ge=0.0, le=1.0)
    subject_tag: Optional[str] = None


class PaperCreateSchema(BaseModel):
    paper_code: str = Field(..., min_length=2, max_length=10)
    year: int = Field(2025, ge=2020, le=2030)
    total_questions: int = Field(65, ge=1, le=100)
    is_multi_session: bool = False
    questions: Optional[List[QuestionSchema]] = None
