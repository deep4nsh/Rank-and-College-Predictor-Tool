from typing import List, Optional, Set
from pydantic import BaseModel, Field


class KeyItemSchema(BaseModel):
    question_id: str
    question_number: Optional[int] = 1
    section: Optional[str] = "CORE"
    question_type: Optional[str] = "MCQ"
    marks_correct: Optional[float] = 1.0
    marks_negative: Optional[float] = 0.3333
    is_mta: bool = False
    valid_options: Optional[List[List[str]]] = None  # e.g., [["A"], ["B"]] or [["A", "C"]]
    nat_min: Optional[float] = None
    nat_max: Optional[float] = None


class AnswerKeyCreateSchema(BaseModel):
    paper_code: str
    version: int = 1
    key_type: str = Field(..., pattern="^(FACULTY_EXAM_DAY|OFFICIAL_IIT)$")
    author_name: str = "PW Faculty Panel"
    items: List[KeyItemSchema]
