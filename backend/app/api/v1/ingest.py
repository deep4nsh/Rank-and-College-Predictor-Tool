"""
Ingestion & Input Channels API:
Handles Digialm response sheet parsing (URL and HTML), bulk CSV/TSV ingestion,
and sample paper template generation for exam-day student input.
"""

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.api.v1.submissions import submit_student_exam_paper
from backend.app.db.models import AnswerKeyItemModel, AnswerKeyModel, QuestionModel
from backend.app.db.session import get_db
from backend.app.schemas.submission import (
    BulkCsvImportRequest,
    BulkCsvImportResponse,
    ResponseItemSchema,
    ResponseSheetParseHtmlRequest,
    ResponseSheetParseUrlRequest,
    ResponseSheetSubmitRequest,
    StudentSubmissionCreateSchema,
)
from backend.app.services.bulk_importer import process_bulk_import
from backend.app.services.response_sheet_parser import (
    ParsedResponseSheet,
    fetch_and_parse_response_sheet_url,
    parse_tcs_response_sheet,
)

router = APIRouter(prefix="/ingest", tags=["Ingestion & Input Channels"])


@router.post("/response-sheet/parse-url")
async def parse_response_sheet_url_endpoint(payload: ResponseSheetParseUrlRequest):
    """
    Parses live TCS iON Digialm response sheet URL without saving,
    returning extracted candidate info and question answers for preview.
    """
    try:
        parsed = await fetch_and_parse_response_sheet_url(payload.url)
        return {
            "status": "success",
            "candidate_name": parsed.candidate_name,
            "roll_number": parsed.roll_number,
            "paper_code": parsed.paper_code,
            "test_date": parsed.test_date,
            "test_time": parsed.test_time,
            "total_questions": parsed.total_questions,
            "attempted_count": parsed.attempted_count,
            "skipped_count": parsed.skipped_count,
            "questions": [q.__dict__ for q in parsed.questions],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/response-sheet/parse-html")
def parse_response_sheet_html_endpoint(payload: ResponseSheetParseHtmlRequest):
    """
    Parses raw HTML text of a TCS iON response sheet without saving.
    """
    try:
        parsed = parse_tcs_response_sheet(payload.html_content)
        return {
            "status": "success",
            "candidate_name": parsed.candidate_name,
            "roll_number": parsed.roll_number,
            "paper_code": parsed.paper_code,
            "test_date": parsed.test_date,
            "test_time": parsed.test_time,
            "total_questions": parsed.total_questions,
            "attempted_count": parsed.attempted_count,
            "skipped_count": parsed.skipped_count,
            "questions": [q.__dict__ for q in parsed.questions],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"HTML parsing error: {str(exc)}")


@router.post("/response-sheet/submit")
async def submit_response_sheet_endpoint(
    payload: ResponseSheetSubmitRequest, db: Session = Depends(get_db)
):
    """
    All-in-One Digialm Ingestion:
    Parses response sheet from URL or HTML, maps responses to active faculty key,
    grades, normalizes, predicts rank, matches colleges/PSUs, and saves to database.
    """
    if payload.url:
        parsed = await fetch_and_parse_response_sheet_url(payload.url)
    elif payload.html_content:
        parsed = parse_tcs_response_sheet(payload.html_content)
    else:
        raise HTTPException(status_code=400, detail="Either 'url' or 'html_content' must be provided.")

    paper_code = parsed.paper_code

    # Check active answer key for this paper
    active_key = (
        db.query(AnswerKeyModel)
        .filter(AnswerKeyModel.paper_code == paper_code, AnswerKeyModel.status == "ACTIVE")
        .order_by(AnswerKeyModel.version.desc())
        .first()
    )

    if not active_key:
        raise HTTPException(
            status_code=400,
            detail=f"No active answer key found for paper {paper_code}. Faculty must publish key v1.",
        )

    # Fetch active key questions to map questions accurately
    key_items = (
        db.query(AnswerKeyItemModel)
        .filter(AnswerKeyItemModel.key_id == active_key.key_id)
        .all()
    )
    key_qids = {item.question_id: item for item in key_items}

    # Map parsed responses to question IDs in key
    response_items = []
    # If question IDs from Digialm match key question IDs:
    parsed_by_qid = {q.question_id: q for q in parsed.questions}

    for item in key_items:
        qid = item.question_id
        parsed_q = parsed_by_qid.get(qid)

        # If not matched by QID, fallback to matching by sequential index
        if not parsed_q:
            # Try finding question with matching number
            q_meta = db.query(QuestionModel).filter(QuestionModel.question_id == qid).first()
            if q_meta and 1 <= q_meta.question_number <= len(parsed.questions):
                parsed_q = parsed.questions[q_meta.question_number - 1]

        if parsed_q and parsed_q.status == "ATTEMPTED":
            response_items.append(
                ResponseItemSchema(
                    question_id=qid,
                    status="ATTEMPTED",
                    marked_options=parsed_q.chosen_options,
                    nat_value=parsed_q.given_answer,
                )
            )
        else:
            response_items.append(
                ResponseItemSchema(
                    question_id=qid,
                    status="SKIPPED",
                    marked_options=None,
                    nat_value=None,
                )
            )

    candidate_name = payload.student_name or parsed.candidate_name or "GATE Candidate"

    sub_schema = StudentSubmissionCreateSchema(
        student_phone=payload.student_phone,
        student_name=candidate_name,
        student_email=payload.student_email,
        student_category=payload.student_category,
        btech_percentage=payload.btech_percentage,
        candidate_age=payload.candidate_age,
        has_valid_ncl=payload.has_valid_ncl,
        pw_batch_id=payload.pw_batch_id or "Digialm_Ingestion",
        paper_code=paper_code,
        session_id=payload.session_id,
        responses=response_items,
    )

    return submit_student_exam_paper(sub_schema, db)


@router.post("/bulk-csv", response_model=BulkCsvImportResponse)
def bulk_csv_import_endpoint(
    payload: BulkCsvImportRequest, db: Session = Depends(get_db)
):
    """
    Offline Counselling Drive Bulk Ingestion:
    Processes CSV or TSV of student records, grades or scores them, and categorizes leads.
    """
    try:
        res = process_bulk_import(payload.csv_content, db)
        return BulkCsvImportResponse(
            total_rows=res.total_rows,
            successful_count=res.successful_count,
            failed_count=res.failed_count,
            errors=res.errors,
            lead_distribution=res.lead_distribution,
            successful_phones=res.successful_phones,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Bulk import failed: {str(exc)}")


@router.get("/sample-paper/{paper_code}")
def get_sample_exam_paper(paper_code: str, db: Session = Depends(get_db)):
    """
    Generates the 65-question GATE paper blueprint for exam-day interactive form.
    Prepopulates question types, sections, and marks based on active key or GATE standards.
    """
    clean_paper = paper_code.upper().strip()

    # Check if questions exist in DB
    existing_questions = (
        db.query(QuestionModel)
        .filter(QuestionModel.paper_code == clean_paper)
        .order_by(QuestionModel.question_number.asc())
        .all()
    )

    questions_data = []

    if existing_questions and len(existing_questions) >= 10:
        for q in existing_questions:
            questions_data.append({
                "question_id": q.question_id,
                "question_number": q.question_number,
                "section": q.section,
                "question_type": q.question_type,
                "marks_correct": q.marks_correct,
                "marks_negative": q.marks_negative,
            })
    else:
        # Standard GATE 65-Question Blueprint
        # Q1-Q5: Aptitude 1 Mark
        for i in range(1, 6):
            questions_data.append({
                "question_id": f"{clean_paper}-{i}",
                "question_number": i,
                "section": "APTITUDE",
                "question_type": "MCQ",
                "marks_correct": 1.0,
                "marks_negative": 0.33,
            })
        # Q6-Q10: Aptitude 2 Marks
        for i in range(6, 11):
            questions_data.append({
                "question_id": f"{clean_paper}-{i}",
                "question_number": i,
                "section": "APTITUDE",
                "question_type": "MCQ",
                "marks_correct": 2.0,
                "marks_negative": 0.66,
            })
        # Q11-Q35: Core 1 Mark
        for i in range(11, 36):
            q_type = "NAT" if i % 4 == 0 else ("MSQ" if i % 5 == 0 else "MCQ")
            neg = 0.0 if q_type in ["NAT", "MSQ"] else 0.33
            questions_data.append({
                "question_id": f"{clean_paper}-{i}",
                "question_number": i,
                "section": "CORE",
                "question_type": q_type,
                "marks_correct": 1.0,
                "marks_negative": neg,
            })
        # Q36-Q65: Core 2 Marks
        for i in range(36, 66):
            q_type = "NAT" if i % 3 == 0 else ("MSQ" if i % 4 == 0 else "MCQ")
            neg = 0.0 if q_type in ["NAT", "MSQ"] else 0.66
            questions_data.append({
                "question_id": f"{clean_paper}-{i}",
                "question_number": i,
                "section": "CORE",
                "question_type": q_type,
                "marks_correct": 2.0,
                "marks_negative": neg,
            })

    return {
        "paper_code": clean_paper,
        "total_questions": len(questions_data),
        "total_marks": 100,
        "duration_minutes": 180,
        "questions": questions_data,
    }
