import csv
import io
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.core.auth import (
    COUNSELLOR_PASSWORD,
    generate_session_token,
    verify_counsellor_access,
)
from backend.app.core.knowledge_base import (
    get_branch_matrix,
    get_ccmt_cutoffs,
    get_coap_cutoffs,
    get_psu_cutoffs,
)
from backend.app.core.matcher import match_options_for_student
from backend.app.db.models import (
    CounsellorCallLogModel,
    EvaluationResultModel,
    StudentSubmissionModel,
)
from backend.app.db.session import get_db
from backend.app.schemas.counsellor import (
    CallLogCreateSchema,
    CallLogResponseSchema,
    LeadSummaryAnalyticsSchema,
)
from backend.app.services.report_generator import generate_student_diagnostic_pdf

router = APIRouter(prefix="/counsellor", tags=["Counsellor Operations"])


class CounsellorLoginSchema(BaseModel):
    passcode: str
    counsellor_name: Optional[str] = "PW Counsellor"


@router.post("/auth/login")
def counsellor_login(payload: CounsellorLoginSchema):
    """
    Authenticates counsellor with passcode (default: 'Councellor@123')
    and returns a signed session token.
    """
    if payload.passcode.strip() != COUNSELLOR_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Invalid counsellor passcode. Access denied.",
        )
    name = (payload.counsellor_name or "PW Counsellor").strip()
    token = generate_session_token(name)
    response = JSONResponse(
        content={
            "status": "authenticated",
            "access_token": token,
            "token_type": "bearer",
            "counsellor_name": name,
        }
    )
    response.set_cookie(
        key="counsellor_token",
        value=token,
        max_age=86400 * 7,
        httponly=False,
        samesite="lax",
    )
    return response


@router.get("/auth/verify")
def verify_session(_auth: str = Depends(verify_counsellor_access)):
    """
    Verifies that the current counsellor session token or passcode is valid.
    """
    return {"status": "authenticated", "valid": True}


@router.get("/students")
def list_students(
    search: Optional[str] = Query(None, description="Search by phone, name, or email"),
    lead_classification: Optional[str] = Query(None, description="SUPER_TOPPER, PSU_AND_TOP_IIT, NIT_PROSPECT, NURTURE_REPEATER"),
    call_disposition: Optional[str] = Query(None, description="PENDING, INTERESTED_IN_BATCH, COAP_COUNSELLING_BOOKED, etc."),
    paper_code: Optional[str] = Query(None),
    min_negative_lost: Optional[float] = Query(None, description="Filter candidates who lost >= X marks to negatives"),
    max_air: Optional[int] = Query(None, description="Filter candidates with predicted AIR <= max_air"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_counsellor_access),
):
    """
    Counsellor operations list with live lead prioritization, negative marking,
    and call disposition filtering.
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

    if call_disposition:
        query = query.filter(StudentSubmissionModel.call_disposition == call_disposition.upper().strip())

    if paper_code:
        query = query.filter(StudentSubmissionModel.paper_code == paper_code.upper().strip())

    if min_negative_lost is not None:
        query = query.filter(EvaluationResultModel.marks_lost_to_negatives >= min_negative_lost)

    if max_air is not None:
        query = query.filter(EvaluationResultModel.predicted_air <= max_air)

    query = query.order_by(EvaluationResultModel.gate_score.desc()).limit(limit)
    rows = query.all()

    results = []
    for sub, ev in rows:
        results.append(
            {
                "submission_id": sub.submission_id,
                "student_phone": sub.student_phone,
                "student_name": sub.student_name,
                "student_email": sub.student_email,
                "paper_code": sub.paper_code,
                "category": sub.student_category,
                "pw_batch_id": sub.pw_batch_id,
                "raw_score": ev.raw_score_total,
                "marks_lost_to_negatives": ev.marks_lost_to_negatives,
                "gate_score": ev.gate_score,
                "predicted_air": ev.predicted_air,
                "air_range": f"{ev.air_range_min} - {ev.air_range_max}",
                "lead_classification": ev.lead_classification,
                "call_disposition": sub.call_disposition or "PENDING",
                "last_contacted_at": sub.last_contacted_at.isoformat() if sub.last_contacted_at else None,
                "submitted_at": sub.submitted_at.isoformat(),
            }
        )

    return {"total": len(results), "students": results}


@router.get("/students/{phone}")
def get_student_counselling_profile(
    phone: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_counsellor_access),
):
    """
    Full Counsellor Diagnostic Profile:
    Returns student details, marks breakdown, complete choice lists
    (COAP, CCMT, PSUs, and Cross-Discipline options), and past call history.
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
        has_valid_ncl=sub.has_valid_ncl if sub.has_valid_ncl is not None else True,
        include_cross_discipline=True,
        historical_coap_data=get_coap_cutoffs(),
        historical_ccmt_data=get_ccmt_cutoffs(),
        historical_psu_data=get_psu_cutoffs(),
        branch_matrix_data=get_branch_matrix(),
    )

    # Fetch chronological call history
    call_logs = (
        db.query(CounsellorCallLogModel)
        .filter(CounsellorCallLogModel.submission_id == sub.submission_id)
        .order_by(CounsellorCallLogModel.logged_at.desc())
        .all()
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
        "call_disposition": sub.call_disposition or "PENDING",
        "last_contacted_at": sub.last_contacted_at.isoformat() if sub.last_contacted_at else None,
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
        "call_history": [
            {
                "log_id": log.log_id,
                "counsellor_name": log.counsellor_name,
                "call_disposition": log.call_disposition,
                "notes": log.notes,
                "follow_up_date": log.follow_up_date,
                "logged_at": log.logged_at.isoformat(),
            }
            for log in call_logs
        ],
    }


@router.post("/students/{phone}/call-log", response_model=CallLogResponseSchema)
def log_student_call(
    phone: str,
    payload: CallLogCreateSchema,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_counsellor_access),
):
    """
    Records a counsellor phone call, updates lead disposition, and sets follow-up reminders.
    """
    clean_phone = phone.strip()
    sub = (
        db.query(StudentSubmissionModel)
        .filter(StudentSubmissionModel.student_phone == clean_phone, StudentSubmissionModel.is_active == True)
        .first()
    )

    if not sub:
        raise HTTPException(status_code=404, detail=f"No active submission found for phone {clean_phone}")

    now_utc = datetime.now(timezone.utc)

    # Create Call Log record
    call_log = CounsellorCallLogModel(
        submission_id=sub.submission_id,
        student_phone=clean_phone,
        counsellor_name=payload.counsellor_name,
        call_disposition=payload.call_disposition,
        notes=payload.notes,
        follow_up_date=payload.follow_up_date,
        logged_at=now_utc,
    )
    db.add(call_log)

    # Update latest status on student submission record
    sub.call_disposition = payload.call_disposition
    sub.last_contacted_at = now_utc

    db.commit()
    db.refresh(call_log)

    return CallLogResponseSchema(
        log_id=call_log.log_id,
        submission_id=call_log.submission_id,
        student_phone=call_log.student_phone,
        counsellor_name=call_log.counsellor_name,
        call_disposition=call_log.call_disposition,
        notes=call_log.notes,
        follow_up_date=call_log.follow_up_date,
        logged_at=call_log.logged_at.isoformat(),
    )


@router.get("/students/{phone}/call-history", response_model=List[CallLogResponseSchema])
def get_student_call_history(
    phone: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_counsellor_access),
):
    """
    Returns chronological call logs for a specific candidate phone number.
    """
    clean_phone = phone.strip()
    logs = (
        db.query(CounsellorCallLogModel)
        .filter(CounsellorCallLogModel.student_phone == clean_phone)
        .order_by(CounsellorCallLogModel.logged_at.desc())
        .all()
    )

    return [
        CallLogResponseSchema(
            log_id=log.log_id,
            submission_id=log.submission_id,
            student_phone=log.student_phone,
            counsellor_name=log.counsellor_name,
            call_disposition=log.call_disposition,
            notes=log.notes,
            follow_up_date=log.follow_up_date,
            logged_at=log.logged_at.isoformat(),
        )
        for log in logs
    ]


@router.get("/students/{phone}/telephony-link")
def get_telephony_links(
    phone: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_counsellor_access),
):
    """
    Generates standard click-to-call deep links (tel:, SIP, and WhatsApp)
    with pre-filled diagnostic report text for instant communication.
    """
    clean_phone = phone.strip()
    # Format phone without leading zeroes
    digits = "".join([c for c in clean_phone if c.isdigit()])
    if len(digits) == 10:
        intl_phone = f"91{digits}"
    else:
        intl_phone = digits

    # Generate summary text for WA links
    row = (
        db.query(StudentSubmissionModel, EvaluationResultModel)
        .join(EvaluationResultModel, StudentSubmissionModel.submission_id == EvaluationResultModel.submission_id)
        .filter(StudentSubmissionModel.student_phone == clean_phone, StudentSubmissionModel.is_active == True)
        .first()
    )

    wa_text = "Hello from Physics Wallah Counselling Team!"
    if row:
        sub, ev = row
        wa_text = (
            f"Hello {sub.student_name}! Here is your PW GATE {sub.paper_code} Diagnostic Summary:\n"
            f"• Raw Score: {ev.raw_score_total:.2f} / 100\n"
            f"• Predicted GATE Score: {ev.gate_score} / 1000\n"
            f"• Estimated AIR: {ev.air_range_min} - {ev.air_range_max}\n"
            f"• Priority: {ev.lead_classification}\n"
            f"Our counselling mentor is available to guide your COAP / CCMT choices."
        )

    encoded_text = urllib.parse.quote(wa_text)

    return {
        "student_phone": clean_phone,
        "tel_uri": f"tel:+{intl_phone}",
        "sip_uri": f"sip:{intl_phone}@pw-telephony.local",
        "wa_web_link": f"https://wa.me/{intl_phone}?text={encoded_text}",
        "wa_api_link": f"https://api.whatsapp.com/send?phone={intl_phone}&text={encoded_text}",
    }


@router.get("/analytics/lead-summary", response_model=LeadSummaryAnalyticsSchema)
def get_lead_summary_analytics(
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_counsellor_access),
):
    """
    Real-time operational dashboard analytics:
    Lead priority counts, disposition status distribution, and negative marks analysis.
    """
    rows = (
        db.query(
            EvaluationResultModel.lead_classification,
            EvaluationResultModel.marks_lost_to_negatives,
            StudentSubmissionModel.call_disposition,
        )
        .join(StudentSubmissionModel, StudentSubmissionModel.submission_id == EvaluationResultModel.submission_id)
        .filter(StudentSubmissionModel.is_active == True)
        .all()
    )

    total = len(rows)
    super_topper = 0
    psu_iit = 0
    nit_prospect = 0
    nurture = 0
    high_neg = 0
    total_neg_lost = 0.0
    disp_counts: Dict[str, int] = {}

    for lead_cls, neg_lost, disp in rows:
        lead_cls_clean = (lead_cls or "NURTURE_REPEATER").upper()
        if lead_cls_clean == "SUPER_TOPPER":
            super_topper += 1
        elif lead_cls_clean == "PSU_AND_TOP_IIT":
            psu_iit += 1
        elif lead_cls_clean == "NIT_PROSPECT":
            nit_prospect += 1
        else:
            nurture += 1

        if neg_lost and neg_lost >= 8.0:
            high_neg += 1
        if neg_lost:
            total_neg_lost += neg_lost

        d_key = (disp or "PENDING").upper()
        disp_counts[d_key] = disp_counts.get(d_key, 0) + 1

    avg_neg = round(total_neg_lost / total, 2) if total > 0 else 0.0

    return LeadSummaryAnalyticsSchema(
        total_submissions=total,
        super_topper_count=super_topper,
        psu_and_top_iit_count=psu_iit,
        nit_prospect_count=nit_prospect,
        nurture_repeater_count=nurture,
        disposition_counts=disp_counts,
        high_negative_marks_count=high_neg,
        avg_marks_lost_to_negatives=avg_neg,
    )


@router.get("/export/csv")
def export_students_csv(
    paper_code: Optional[str] = Query(None),
    lead_classification: Optional[str] = Query(None),
    call_disposition: Optional[str] = Query(None),
    min_negative_lost: Optional[float] = Query(None),
    max_air: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_counsellor_access),
):
    """
    Exports filtered candidate leads to a formatted CSV file for offline calling teams.
    """
    query = (
        db.query(StudentSubmissionModel, EvaluationResultModel)
        .join(EvaluationResultModel, StudentSubmissionModel.submission_id == EvaluationResultModel.submission_id)
        .filter(StudentSubmissionModel.is_active == True)
    )

    if paper_code:
        query = query.filter(StudentSubmissionModel.paper_code == paper_code.upper().strip())
    if lead_classification:
        query = query.filter(EvaluationResultModel.lead_classification == lead_classification.upper().strip())
    if call_disposition:
        query = query.filter(StudentSubmissionModel.call_disposition == call_disposition.upper().strip())
    if min_negative_lost is not None:
        query = query.filter(EvaluationResultModel.marks_lost_to_negatives >= min_negative_lost)
    if max_air is not None:
        query = query.filter(EvaluationResultModel.predicted_air <= max_air)

    query = query.order_by(EvaluationResultModel.gate_score.desc())
    rows = query.all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header Row
    writer.writerow([
        "Student Name",
        "Phone",
        "Email",
        "Category",
        "Paper Code",
        "Batch",
        "Raw Score",
        "Marks Lost Negatives",
        "Predicted GATE Score",
        "Estimated AIR",
        "AIR Band Min",
        "AIR Band Max",
        "Lead Classification",
        "Call Disposition",
        "Last Contacted At",
        "Submitted At",
    ])

    for sub, ev in rows:
        writer.writerow([
            sub.student_name,
            sub.student_phone,
            sub.student_email or "",
            sub.student_category,
            sub.paper_code,
            sub.pw_batch_id or "",
            f"{ev.raw_score_total:.2f}",
            f"{ev.marks_lost_to_negatives:.2f}",
            ev.gate_score,
            ev.predicted_air,
            ev.air_range_min,
            ev.air_range_max,
            ev.lead_classification,
            sub.call_disposition or "PENDING",
            sub.last_contacted_at.isoformat() if sub.last_contacted_at else "",
            sub.submitted_at.isoformat(),
        ])

    output.seek(0)
    filename = f"PW_GATE_Leads_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/students/{phone}/whatsapp-summary")
def generate_whatsapp_summary(
    phone: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_counsellor_access),
):
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
        has_valid_ncl=sub.has_valid_ncl if sub.has_valid_ncl is not None else True,
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
def download_student_diagnostic_pdf(
    phone: str,
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_counsellor_access),
):
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
        has_valid_ncl=sub.has_valid_ncl if sub.has_valid_ncl is not None else True,
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
