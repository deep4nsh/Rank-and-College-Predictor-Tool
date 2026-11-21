from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.app.db.models import EvaluationResultModel, StudentSubmissionModel
from backend.app.db.session import get_db

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


@router.get("/students/{phone}/whatsapp-summary")
def generate_whatsapp_summary(phone: str, db: Session = Depends(get_db)):
    """
    Generates a 1-click formatted summary for counsellors to paste directly on WhatsApp.
    """
    row = (
        db.query(StudentSubmissionModel, EvaluationResultModel)
        .join(EvaluationResultModel, StudentSubmissionModel.submission_id == EvaluationResultModel.submission_id)
        .filter(StudentSubmissionModel.student_phone == phone.strip(), StudentSubmissionModel.is_active == True)
        .first()
    )

    if not row:
        return {"error": "Student submission not found"}

    sub, ev = row

    summary_text = (
        f"🎯 *PW GATE Academic & Counselling Diagnostic*\n\n"
        f"👤 *Candidate:* {sub.student_name}\n"
        f"📱 *Phone:* {sub.student_phone}\n"
        f"📚 *Branch:* GATE {sub.paper_code}\n\n"
        f"📊 *Performance Summary:*\n"
        f"• Raw Score: {ev.raw_score_total:.2f} / 100\n"
        f"• Marks Lost to Negatives: -{ev.marks_lost_to_negatives:.2f}\n"
        f"• Predicted GATE Score: {ev.gate_score} / 1000\n"
        f"• Estimated AIR Band: {ev.air_range_min} - {ev.air_range_max}\n"
        f"• Priority Classification: *{ev.lead_classification}*\n\n"
        f"💡 *Counsellor Recommendation:*\n"
    )

    if ev.gate_score >= 700:
        summary_text += "• Eligible for top IITs Direct/Interview M.Tech and PSU shortlist (IOCL/ONGC/NTPC).\n"
    elif ev.gate_score >= 550:
        summary_text += "• Strong contender for top NITs (Trichy, Surathkal, Warangal) core branches.\n"
    else:
        summary_text += "• Recommend reviewing marks lost to negative marking; strong candidate for target improvement batch.\n"

    summary_text += "\n_Powered by Physics Wallah In-House Counselling Operations Engine_"

    return {"phone": sub.student_phone, "whatsapp_text": summary_text}
