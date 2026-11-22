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
from backend.app.core.knowledge_base import (
    get_branch_matrix,
    get_ccmt_cutoffs,
    get_coap_cutoffs,
    get_psu_cutoffs,
)
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
from backend.app.schemas.key import AnswerKeyCreateSchema

router = APIRouter(prefix="/keys", tags=["Answer Keys"])


@router.post("")
def create_answer_key(payload: AnswerKeyCreateSchema, db: Session = Depends(get_db)):
    """
    Creates and publishes an answer key (PW Faculty or Official IIT).
    Auto-provisions QuestionModel records if not already in DB.
    """
    paper_code = payload.paper_code.upper().strip()

    # Verify paper exists
    paper = db.query(PaperModel).filter(PaperModel.paper_code == paper_code).first()
    if not paper:
        paper = PaperModel(paper_code=paper_code, year=2025)
        db.add(paper)
        db.commit()

    # Auto-provision QuestionModel records to enforce foreign key integrity
    existing_q_ids = {
        q.question_id
        for q in db.query(QuestionModel.question_id).filter(QuestionModel.paper_code == paper_code).all()
    }

    for idx, item in enumerate(payload.items):
        if item.question_id not in existing_q_ids:
            new_q = QuestionModel(
                question_id=item.question_id,
                paper_code=paper_code,
                question_number=item.question_number or (idx + 1),
                section=item.section or "CORE",
                question_type=item.question_type or "MCQ",
                marks_correct=item.marks_correct or 1.0,
                marks_negative=item.marks_negative or 0.3333,
            )
            db.add(new_q)
            existing_q_ids.add(item.question_id)

    db.flush()

    # Deactivate previous active keys if this is a newer version
    db.query(AnswerKeyModel).filter(
        AnswerKeyModel.paper_code == paper_code, AnswerKeyModel.status == "ACTIVE"
    ).update({"status": "ARCHIVED"})

    # Create key
    new_key = AnswerKeyModel(
        paper_code=paper_code,
        version=payload.version,
        key_type=payload.key_type,
        author_name=payload.author_name,
        status="ACTIVE",
    )
    db.add(new_key)
    db.flush()

    for item in payload.items:
        key_item = AnswerKeyItemModel(
            key_id=new_key.key_id,
            question_id=item.question_id,
            is_mta=item.is_mta,
            valid_options_json=json.dumps(item.valid_options) if item.valid_options else None,
            nat_min=item.nat_min,
            nat_max=item.nat_max,
        )
        db.add(key_item)

    db.commit()
    db.refresh(new_key)

    return {
        "status": "success",
        "key_id": new_key.key_id,
        "paper_code": new_key.paper_code,
        "version": new_key.version,
        "key_type": new_key.key_type,
        "total_items": len(payload.items),
    }


@router.get("/{paper_code}/active")
def get_active_key(paper_code: str, db: Session = Depends(get_db)):
    """
    Retrieves the current active answer key for a given paper.
    """
    key = (
        db.query(AnswerKeyModel)
        .filter(AnswerKeyModel.paper_code == paper_code.upper().strip(), AnswerKeyModel.status == "ACTIVE")
        .order_by(AnswerKeyModel.version.desc())
        .first()
    )
    if not key:
        raise HTTPException(status_code=404, detail=f"No active answer key found for paper {paper_code}")

    return {
        "key_id": key.key_id,
        "paper_code": key.paper_code,
        "version": key.version,
        "key_type": key.key_type,
        "author": key.author_name,
        "published_at": key.published_at.isoformat(),
    }


@router.post("/{key_id}/re-evaluate")
def re_evaluate_submissions(key_id: str, db: Session = Depends(get_db)):
    """
    Batch Re-Evaluation Worker:
    When an answer key is updated (e.g. Official IIT Key released or Faculty Key revised),
    this re-evaluates all existing student submissions against the new key in a single batch.
    """
    target_key = db.query(AnswerKeyModel).filter(AnswerKeyModel.key_id == key_id).first()
    if not target_key:
        raise HTTPException(status_code=404, detail=f"Answer key {key_id} not found")

    paper_code = target_key.paper_code.upper()

    # Load key items & question rules
    key_items = db.query(AnswerKeyItemModel).filter(AnswerKeyItemModel.key_id == key_id).all()
    q_map = {q.question_id: q for q in db.query(QuestionModel).filter(QuestionModel.paper_code == paper_code).all()}

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

    # Fetch all active submissions for this paper
    active_subs = (
        db.query(StudentSubmissionModel)
        .filter(StudentSubmissionModel.paper_code == paper_code, StudentSubmissionModel.is_active == True)
        .all()
    )

    if not active_subs:
        return {"status": "success", "message": "No active student submissions found for this paper", "count": 0}

    sub_ids = [s.submission_id for s in active_subs]

    # Pre-fetch existing evaluations in 1 bulk query
    eval_map = {
        ev.submission_id: ev
        for ev in db.query(EvaluationResultModel)
        .filter(EvaluationResultModel.submission_id.in_(sub_ids))
        .all()
    }

    # Pre-fetch all responses in 1 bulk query and group by submission_id
    all_responses = (
        db.query(StudentResponseModel)
        .filter(StudentResponseModel.submission_id.in_(sub_ids))
        .all()
    )
    responses_by_sub = {}
    for r in all_responses:
        responses_by_sub.setdefault(r.submission_id, []).append(r)

    rank_engine = MonotonicRankEngine(paper_code)
    coap_data = get_coap_cutoffs()
    ccmt_data = get_ccmt_cutoffs()
    psu_data = get_psu_cutoffs()
    branch_matrix = get_branch_matrix()

    re_evaluated_count = 0
    deltas = []

    # Pass 1: Grade all submissions against updated key rules and collect raw scores per session
    graded_candidates = []
    session_scores_map = {}
    for sub in active_subs:
        existing_eval = eval_map.get(sub.submission_id)
        responses = responses_by_sub.get(sub.submission_id, [])

        if not responses:
            # Direct score import without individual question choices
            # Preserve existing raw scores intact while updating normalization!
            raw_sc = existing_eval.raw_score_total if existing_eval else 0.0
            graded_candidates.append((sub, None, raw_sc))
            session_scores_map.setdefault(sub.session_id, []).append(raw_sc)
            continue

        student_answers = [
            StudentAnswer(
                question_id=r.question_id,
                status=r.status,
                marked_options=json.loads(r.student_options_json) if r.student_options_json else None,
                nat_value=r.student_nat_value,
            )
            for r in responses
        ]
        summary = grade_paper(rules, student_answers)
        graded_candidates.append((sub, summary, summary.total_raw_score))
        session_scores_map.setdefault(sub.session_id, []).append(summary.total_raw_score)

    # Pass 2: Normalize with updated shift distributions, predict rank, and match options
    for sub, summary, raw_score in graded_candidates:
        norm_result = normalize_gate_score(
            paper_code=paper_code,
            session_id=sub.session_id,
            raw_score=raw_score,
            all_sessions_scores=session_scores_map,
        )

        # Predict rank
        rank_pred = rank_engine.predict_rank(norm_result.normalized_marks)

        # Match recommendations
        rec_summary = match_options_for_student(
            gate_score=norm_result.gate_score,
            predicted_air=rank_pred.predicted_air,
            paper_code=paper_code,
            category=sub.student_category,
            btech_percentage=sub.btech_percentage,
            candidate_age=sub.candidate_age,
            has_valid_ncl=sub.has_valid_ncl,
            include_cross_discipline=True,
            historical_coap_data=coap_data,
            historical_ccmt_data=ccmt_data,
            historical_psu_data=psu_data,
            branch_matrix_data=branch_matrix,
        )

        # Check existing evaluation for score delta calculation
        existing_eval = eval_map.get(sub.submission_id)

        old_score = existing_eval.raw_score_total if existing_eval else raw_score
        delta = raw_score - old_score
        deltas.append(delta)

        if existing_eval:
            if summary is not None:
                existing_eval.key_id = key_id
                existing_eval.raw_score_total = summary.total_raw_score
                existing_eval.raw_score_aptitude = summary.aptitude_score
                existing_eval.raw_score_core = summary.core_score
                existing_eval.marks_lost_to_negatives = summary.marks_lost_to_negatives
                existing_eval.correct_count = summary.correct_count
                existing_eval.incorrect_count = summary.incorrect_count
                existing_eval.unattempted_count = summary.unattempted_count
            existing_eval.normalized_marks = norm_result.normalized_marks
            existing_eval.gate_score = norm_result.gate_score
            existing_eval.predicted_air = rank_pred.predicted_air
            existing_eval.air_range_min = rank_pred.air_range_min
            existing_eval.air_range_max = rank_pred.air_range_max
            existing_eval.lead_classification = rec_summary.lead_classification
        else:
            new_eval = EvaluationResultModel(
                submission_id=sub.submission_id,
                key_id=key_id if summary is not None else None,
                raw_score_total=summary.total_raw_score if summary is not None else raw_score,
                raw_score_aptitude=summary.aptitude_score if summary is not None else 0.0,
                raw_score_core=summary.core_score if summary is not None else 0.0,
                marks_lost_to_negatives=summary.marks_lost_to_negatives if summary is not None else 0.0,
                correct_count=summary.correct_count if summary is not None else 0,
                incorrect_count=summary.incorrect_count if summary is not None else 0,
                unattempted_count=summary.unattempted_count if summary is not None else 0,
                normalized_marks=norm_result.normalized_marks,
                gate_score=norm_result.gate_score,
                predicted_air=rank_pred.predicted_air,
                air_range_min=rank_pred.air_range_min,
                air_range_max=rank_pred.air_range_max,
                lead_classification=rec_summary.lead_classification,
            )
            db.add(new_eval)

        re_evaluated_count += 1

    db.commit()

    avg_delta = float(sum(deltas) / len(deltas)) if deltas else 0.0

    return {
        "status": "success",
        "key_id": key_id,
        "key_version": target_key.version,
        "key_type": target_key.key_type,
        "re_evaluated_count": re_evaluated_count,
        "avg_score_delta": round(avg_delta, 3),
    }
