from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from backend.app.core.knowledge_base import (
    get_branch_matrix,
    get_ccmt_cutoffs,
    get_coap_cutoffs,
    get_psu_cutoffs,
)
from backend.app.core.matcher import match_options_for_student
from backend.app.db.models import EvaluationResultModel, StudentSubmissionModel
from backend.app.db.session import get_db
from backend.app.services.report_generator import generate_student_diagnostic_pdf

router = APIRouter(prefix="/counsellor", tags=["Counsellor Operations"])


@router.get("/students")
def list_students(
    search: Optional[str] = Query(None, description="Search by phone, name, or email"),
    lead_classification: Optional[str] = Query(None, description="SUPER_TOPPER, PSU_AND_TOP_IIT, NIT_PROSPECT, NURTURE_REPEATER"),
    paper_code: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    Counsellor operations list with live lead prioritization filter.
    """
    query = (
        db.query(StudentSubmissionModel, EvaluationResultModel)
        .join(EvaluationResultModel, StudentSubmissionModel.submission_id == EvaluationResultModel.submission_id)
        .filter(StudentSubmissionModel.is_active == True)
    )

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            (StudentSubmissionModel.student_phone.like(search_pattern))
            | (StudentSubmissionModel.student_name.ilike(search_pattern))
            | (StudentSubmissionModel.student_email.ilike(search_pattern))
        )

    if lead_classification:
        query = query.filter(EvaluationResultModel.lead_classification == lead_classification.upper().strip())

    if paper_code:
        query = query.filter(StudentSubmissionModel.paper_code == paper_code.upper().strip())

    query = query.order_by(EvaluationResultModel.gate_score.desc()).limit(limit)
    rows = query.all()

    results = []
    for sub, ev in rows:
        results.append(
            {
                "submission_id": sub.submission_id,
                "student_phone": sub.student_phone,
                "student_name": sub.student_name,
                "paper_code": sub.paper_code,
                "category": sub.student_category,
                "pw_batch_id": sub.pw_batch_id,
                "raw_score": ev.raw_score_total,
                "marks_lost_to_negatives": ev.marks_lost_to_negatives,
                "gate_score": ev.gate_score,
                "predicted_air": ev.predicted_air,
                "air_range": f"{ev.air_range_min} - {ev.air_range_max}",
                "lead_classification": ev.lead_classification,
                "submitted_at": sub.submitted_at.isoformat(),
            }
        )

    return {"total": len(results), "students": results}


@router.get("/students/{phone}")
def get_student_counselling_profile(phone: str, db: Session = Depends(get_db)):
    """
    Full Counsellor Diagnostic Profile:
    Returns student details, marks breakdown, and complete choice lists
    (COAP, CCMT, PSUs, and Cross-Discipline options) for live counselling calls.
    """
    row = (
        db.query(StudentSubmissionModel, EvaluationResultModel)
        .join(EvaluationResultModel, StudentSubmissionModel.submission_id == EvaluationResultModel.submission_id)
        .filter(StudentSubmissionModel.student_phone == phone.strip(), StudentSubmissionModel.is_active == True)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail=f"No active submission found for phone {phone}")

    sub, ev = row

    # Generate full real-time choice matching using Phase 2 knowledge base
    summary = match_options_for_student(
        gate_score=ev.gate_score,
        predicted_air=ev.predicted_air,
        paper_code=sub.paper_code,
        category=sub.student_category,
        btech_percentage=sub.btech_percentage or 70.0,
        candidate_age=sub.candidate_age or 23,
        has_valid_ncl=sub.has_valid_ncl,
        include_cross_discipline=True,
        historical_coap_data=get_coap_cutoffs(),
        historical_ccmt_data=get_ccmt_cutoffs(),
        historical_psu_data=get_psu_cutoffs(),
        branch_matrix_data=get_branch_matrix(),
    )

    return {
        "student_phone": sub.student_phone,
        "student_name": sub.student_name,
        "student_email": sub.student_email,
        "category": sub.student_category,
        "btech_percentage": sub.btech_percentage,
        "candidate_age": sub.candidate_age,
        "has_valid_ncl": sub.has_valid_ncl,
        "pw_batch_id": sub.pw_batch_id,
        "paper_code": sub.paper_code,
        "raw_score_total": ev.raw_score_total,
        "raw_score_aptitude": ev.raw_score_aptitude,
        "raw_score_core": ev.raw_score_core,
        "marks_lost_to_negatives": ev.marks_lost_to_negatives,
        "correct_count": ev.correct_count,
        "incorrect_count": ev.incorrect_count,
        "unattempted_count": ev.unattempted_count,
        "normalized_marks": ev.normalized_marks,
        "gate_score": ev.gate_score,
        "predicted_air": ev.predicted_air,
        "air_range": f"{ev.air_range_min} - {ev.air_range_max}",
        "lead_classification": ev.lead_classification,
        "coap_options": [o.__dict__ for o in summary.coap_options],
        "ccmt_options": [o.__dict__ for o in summary.ccmt_options],
        "psu_options": [o.__dict__ for o in summary.psu_options],
        "interdisciplinary_options": [o.__dict__ for o in summary.interdisciplinary_options],
    }


@router.get("/students/{phone}/whatsapp-summary")
def generate_whatsapp_summary(phone: str, db: Session = Depends(get_db)):
    """
    Generates a 1-click dynamic summary for counsellors to share via WhatsApp,
    featuring candidate diagnostic metrics and their specific Safe/Target colleges.
    """
    row = (
        db.query(StudentSubmissionModel, EvaluationResultModel)
        .join(EvaluationResultModel, StudentSubmissionModel.submission_id == EvaluationResultModel.submission_id)
        .filter(StudentSubmissionModel.student_phone == phone.strip(), StudentSubmissionModel.is_active == True)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="Student submission not found")

    sub, ev = row

    # Live matching
    summary = match_options_for_student(
        gate_score=ev.gate_score,
        predicted_air=ev.predicted_air,
        paper_code=sub.paper_code,
        category=sub.student_category,
        btech_percentage=sub.btech_percentage or 70.0,
        candidate_age=sub.candidate_age or 23,
        has_valid_ncl=sub.has_valid_ncl,
        include_cross_discipline=True,
        historical_coap_data=get_coap_cutoffs(),
        historical_ccmt_data=get_ccmt_cutoffs(),
        historical_psu_data=get_psu_cutoffs(),
        branch_matrix_data=get_branch_matrix(),
    )

    # Format top choices
    safe_coap = [f"{o.institution_name} ({o.program_name})" for o in summary.coap_options if o.match_tier == "SAFE"][:2]
    target_coap = [f"{o.institution_name} ({o.program_name})" for o in summary.coap_options if o.match_tier == "TARGET"][:2]
    safe_ccmt = [f"{o.institution_name} ({o.program_name})" for o in summary.ccmt_options if o.match_tier == "SAFE"][:2]
    psu_eligible = [f"{p.psu_name} ({p.post_name})" for p in summary.psu_options if p.is_eligible][:2]
    interdisc = [f"{o.institution_name} ({o.program_name})" for o in summary.interdisciplinary_options][:2]

    msg = (
        f"🎯 *PW GATE Academic & Counselling Diagnostic*\n\n"
        f"👤 *Candidate:* {sub.student_name}\n"
        f"📱 *Phone:* {sub.student_phone}\n"
        f"📚 *Branch:* GATE {sub.paper_code} | *Category:* {sub.student_category}\n\n"
        f"📊 *Performance Summary:*\n"
        f"• Raw Score: {ev.raw_score_total:.2f} / 100\n"
        f"• Marks Lost to Negatives: -{ev.marks_lost_to_negatives:.2f}\n"
        f"• Predicted GATE Score: {ev.gate_score} / 1000\n"
        f"• Estimated AIR Band: {ev.air_range_min} - {ev.air_range_max}\n"
        f"• Lead Priority: *{ev.lead_classification}*\n\n"
        f"🏛️ *Top Matching Recommendations:*\n"
    )

    if safe_coap:
        msg += f"• *Safe (IITs/COAP):* {', '.join(safe_coap)}\n"
    if target_coap:
        msg += f"• *Target (IITs/COAP):* {', '.join(target_coap)}\n"
    if psu_eligible:
        msg += f"• *PSU Shortlist Chance:* {', '.join(psu_eligible)}\n"
    if safe_ccmt:
        msg += f"• *Safe (NITs/CCMT):* {', '.join(safe_ccmt)}\n"
    if interdisc:
        msg += f"• *Cross-Discipline:* {', '.join(interdisc)}\n"

    if not safe_coap and not target_coap and not safe_ccmt:
        msg += "• *Target Batches:* Advise reviewing negative marks; strong candidate for PW rank-improvement batches.\n"

    msg += "\n_Powered by Physics Wallah In-House Counselling Operations Engine_"

    return {"phone": sub.student_phone, "whatsapp_text": msg}


@router.get("/students/{phone}/pdf")
def download_student_diagnostic_pdf(phone: str, db: Session = Depends(get_db)):
    """
    Generates and streams a 1-page PW-branded Student Diagnostic PDF scorecard
    for counselling sessions and direct candidate delivery.
    """
    row = (
        db.query(StudentSubmissionModel, EvaluationResultModel)
        .join(EvaluationResultModel, StudentSubmissionModel.submission_id == EvaluationResultModel.submission_id)
        .filter(StudentSubmissionModel.student_phone == phone.strip(), StudentSubmissionModel.is_active == True)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="Student submission not found")

    sub, ev = row

    summary = match_options_for_student(
        gate_score=ev.gate_score,
        predicted_air=ev.predicted_air,
        paper_code=sub.paper_code,
        category=sub.student_category,
        btech_percentage=sub.btech_percentage or 70.0,
        candidate_age=sub.candidate_age or 23,
        has_valid_ncl=sub.has_valid_ncl,
        include_cross_discipline=True,
        historical_coap_data=get_coap_cutoffs(),
        historical_ccmt_data=get_ccmt_cutoffs(),
        historical_psu_data=get_psu_cutoffs(),
        branch_matrix_data=get_branch_matrix(),
    )

    student_dict = {
        "name": sub.student_name,
        "phone": sub.student_phone,
        "email": sub.student_email,
        "category": sub.student_category,
        "paper_code": sub.paper_code,
        "batch": sub.pw_batch_id or "PW Student",
        "has_valid_ncl": sub.has_valid_ncl,
    }

    eval_dict = {
        "raw_score_total": ev.raw_score_total,
        "raw_score_aptitude": ev.raw_score_aptitude,
        "raw_score_core": ev.raw_score_core,
        "marks_lost_to_negatives": ev.marks_lost_to_negatives,
        "gate_score": ev.gate_score,
        "predicted_air": ev.predicted_air,
        "air_range": f"{ev.air_range_min} - {ev.air_range_max}",
        "lead_classification": ev.lead_classification,
    }

    matches_dict = {
        "coap_options": [o.__dict__ for o in summary.coap_options],
        "ccmt_options": [o.__dict__ for o in summary.ccmt_options],
        "psu_options": [o.__dict__ for o in summary.psu_options],
        "interdisciplinary_options": [o.__dict__ for o in summary.interdisciplinary_options],
    }

    pdf_buffer = generate_student_diagnostic_pdf(student_dict, eval_dict, matches_dict)

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=PW_GATE_Diagnostic_{phone}.pdf"},
    )
