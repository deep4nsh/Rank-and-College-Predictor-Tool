from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ResponseItemSchema(BaseModel):
    question_id: str
    status: str = Field("ATTEMPTED", pattern="^(ATTEMPTED|SKIPPED|MARKED_REVIEW|NOT_ATTEMPTED)$")
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


class ResponseSheetParseUrlRequest(BaseModel):
    url: str = Field(..., description="Public TCS iON Digialm response sheet URL")


class ResponseSheetParseHtmlRequest(BaseModel):
    html_content: str = Field(..., description="Raw HTML string of response sheet")


class ResponseSheetSubmitRequest(BaseModel):
    url: Optional[str] = None
    html_content: Optional[str] = None
    student_phone: str = Field(..., pattern=r"^[6-9]\d{9}$", description="10-digit Indian Mobile")
    student_name: Optional[str] = None
    student_email: Optional[str] = None
    student_category: str = Field("GEN", pattern="^(GEN|OBC_NCL|OBC|EWS|SC|ST|PWD)$")
    btech_percentage: float = Field(70.0, ge=40.0, le=100.0)
    candidate_age: int = Field(22, ge=18, le=45)
    has_valid_ncl: bool = True
    pw_batch_id: Optional[str] = None
    session_id: int = Field(1, ge=1, le=4)


class BulkCsvImportRequest(BaseModel):
    csv_content: str = Field(..., description="Raw CSV or TSV string")


class BulkCsvImportResponse(BaseModel):
    total_rows: int
    successful_count: int
    failed_count: int
    errors: List[Dict[str, Any]]
    lead_distribution: Dict[str, int]
    successful_phones: List[str]
