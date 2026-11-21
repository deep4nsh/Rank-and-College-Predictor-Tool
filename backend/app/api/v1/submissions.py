from decimal import Decimal
from fractions import Fraction
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.core.grader import QuestionRule, StudentAnswer, grade_paper
from backend.app.core.matcher import match_options_for_student
from backend.app.core.normalizer import normalize_gate_score
from backend.app.core.rank_spline import MonotonicRankEngine
from backend.app.db.models import (
    AnswerKeyItemModel,
    AnswerKeyModel,
    EvaluationResultModel,
    PaperModel,
    QuestionModel,
    StudentResponseModel,
    StudentSubmissionModel,
)
from backend.app.db.session import get_db
from backend.app.schemas.submission import StudentSubmissionCreateSchema

router = APIRouter(prefix="/submissions", tags=["Student Submissions"])

DATA_DIR = Path(__file__).resolve().parents[4] / "data"


def load_json(filename: str):
    p = DATA_DIR / filename
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def get_live_sessions_scores(paper_code: str, db: Session) -> dict:
    """
    Fetches all active candidate raw scores grouped by shift/session
    for live dynamic multi-session normalization on exam day.
    """
    rows = (
        db.query(StudentSubmissionModel.session_id, EvaluationResultModel.raw_score_total)
        .join(EvaluationResultModel, StudentSubmissionModel.submission_id == EvaluationResultModel.submission_id)
        .filter(StudentSubmissionModel.paper_code == paper_code.upper().strip(), StudentSubmissionModel.is_active == True)
        .all()
    )
    res = {}
    for s_id, score in rows:
        res.setdefault(s_id, []).append(score)
    return res


@router.post("")
def submit_student_exam_paper(
    payload: StudentSubmissionCreateSchema, db: Session = Depends(get_db)
):
    """
    Primary Exam Day Endpoint:
    Receives student marked paper, auto-evaluates against active faculty key,
    computes scores, predicted rank, and college/PSU matches.
    """
    clean_paper = payload.paper_code.upper().strip()

    # Check active key
    active_key = (
        db.query(AnswerKeyModel)
        .filter(AnswerKeyModel.paper_code == clean_paper, AnswerKeyModel.status == "ACTIVE")
        .order_by(AnswerKeyModel.version.desc())
        .first()
    )

    if not active_key:
        raise HTTPException(
            status_code=400,
            detail=f"No active answer key available for {clean_paper}. Faculty must publish key v1.",
        )

    # Deactivate any previous submissions for this student on this paper (idempotent upsert)
    db.query(StudentSubmissionModel).filter(
        StudentSubmissionModel.student_phone == payload.student_phone,
        StudentSubmissionModel.paper_code == clean_paper,
    ).update({"is_active": False})

    # Create submission record
    submission = StudentSubmissionModel(
        student_phone=payload.student_phone,
        student_name=payload.student_name,
        student_email=payload.student_email,
        student_category=payload.student_category,
        btech_percentage=payload.btech_percentage,
        candidate_age=payload.candidate_age,
        has_valid_ncl=payload.has_valid_ncl,
        pw_batch_id=payload.pw_batch_id,
        paper_code=clean_paper,
        session_id=payload.session_id,
        is_active=True,
    )
    db.add(submission)
    db.flush()

    # Store individual student responses
    for resp in payload.responses:
        r_model = StudentResponseModel(
            submission_id=submission.submission_id,
            question_id=resp.question_id,
            status=resp.status,
            student_options_json=json.dumps(resp.marked_options) if resp.marked_options else None,
            student_nat_value=resp.nat_value,
        )
        db.add(r_model)

    # Build question rules from active key
    key_items = db.query(AnswerKeyItemModel).filter(AnswerKeyItemModel.key_id == active_key.key_id).all()
    q_map = {q.question_id: q for q in db.query(QuestionModel).filter(QuestionModel.paper_code == clean_paper).all()}

    rules = []
    for item in key_items:
        q_meta = q_map.get(item.question_id)
        q_type = q_meta.question_type if q_meta else "MCQ"
        section = q_meta.section if q_meta else "CORE"
        marks_corr = Fraction(2, 1) if (q_meta and q_meta.marks_correct == 2.0) else Fraction(1, 1)
        marks_neg = Fraction(2, 3) if marks_corr == 2 else Fraction(1, 3)

        valid_mcq = []
        valid_msq = []
        if item.valid_options_json:
            parsed = json.loads(item.valid_options_json)
            if q_type == "MCQ":
                valid_mcq = [opt[0] for opt in parsed if opt]
            elif q_type == "MSQ":
                valid_msq = [{str(o) for o in opt_set} for opt_set in parsed]

        rules.append(
            QuestionRule(
                question_id=item.question_id,
                question_number=q_meta.question_number if q_meta else 1,
                question_type=q_type,
                section=section,
                marks_correct=marks_corr,
                marks_negative=Fraction(0, 1) if q_type in ["MSQ", "NAT"] else marks_neg,
                is_mta=item.is_mta,
                valid_mcq_options=valid_mcq,
                valid_msq_sets=valid_msq,
                nat_min=Decimal(str(item.nat_min)) if item.nat_min is not None else None,
                nat_max=Decimal(str(item.nat_max)) if item.nat_max is not None else None,
            )
        )

    # Convert student responses to grader format
    student_answers = [
        StudentAnswer(
            question_id=r.question_id,
            status=r.status,
            marked_options=r.marked_options,
            nat_value=r.nat_value,
        )
        for r in payload.responses
    ]

    # Evaluate paper
    summary = grade_paper(rules, student_answers)

    # Fetch live session scores from DB to dynamically calculate shift stats
    live_scores = get_live_sessions_scores(clean_paper, db)
    live_scores.setdefault(payload.session_id, []).append(summary.total_raw_score)

    # Normalization & GATE score calculation
    norm_result = normalize_gate_score(
        paper_code=clean_paper,
        session_id=payload.session_id,
        raw_score=summary.total_raw_score,
        all_sessions_scores=live_scores,
    )

    # Predict rank via PCHIP spline
    rank_engine = MonotonicRankEngine(clean_paper)
    rank_pred = rank_engine.predict_rank(norm_result.normalized_marks)

    # Match colleges & PSUs
    rec_summary = match_options_for_student(
        gate_score=norm_result.gate_score,
        predicted_air=rank_pred.predicted_air,
        paper_code=clean_paper,
        category=payload.student_category,
        btech_percentage=payload.btech_percentage,
        candidate_age=payload.candidate_age,
        has_valid_ncl=payload.has_valid_ncl,
        historical_coap_data=load_json("cutoffs_coap.json"),
        historical_ccmt_data=load_json("cutoffs_ccmt.json"),
        historical_psu_data=load_json("cutoffs_psu.json"),
    )

    # Store Evaluation Result in DB
    eval_model = EvaluationResultModel(
        submission_id=submission.submission_id,
        key_id=active_key.key_id,
        raw_score_total=summary.total_raw_score,
        raw_score_aptitude=summary.aptitude_score,
        raw_score_core=summary.core_score,
        marks_lost_to_negatives=summary.marks_lost_to_negatives,
        correct_count=summary.correct_count,
        incorrect_count=summary.incorrect_count,
        unattempted_count=summary.unattempted_count,
        normalized_marks=norm_result.normalized_marks,
        gate_score=norm_result.gate_score,
        predicted_air=rank_pred.predicted_air,
        air_range_min=rank_pred.air_range_min,
        air_range_max=rank_pred.air_range_max,
        lead_classification=rec_summary.lead_classification,
    )
    db.add(eval_model)
    db.commit()

    return {
        "status": "success",
        "submission_id": submission.submission_id,
        "key_version": active_key.version,
        "key_type": active_key.key_type,
        "raw_score_total": summary.total_raw_score,
        "raw_score_aptitude": summary.aptitude_score,
        "raw_score_core": summary.core_score,
        "marks_lost_to_negatives": summary.marks_lost_to_negatives,
        "normalized_marks": norm_result.normalized_marks,
        "gate_score": norm_result.gate_score,
        "predicted_air": rank_pred.predicted_air,
        "air_range": f"{rank_pred.air_range_min} - {rank_pred.air_range_max}",
        "lead_classification": rec_summary.lead_classification,
        "coap_matches": [o.__dict__ for o in rec_summary.coap_options],
        "ccmt_matches": [o.__dict__ for o in rec_summary.ccmt_options],
        "psu_matches": [o.__dict__ for o in rec_summary.psu_options],
    }
