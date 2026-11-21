"""
Bulk CSV / TSV Importer for Offline Counselling Drives:
Processes bulk spreadsheets of student responses or scores, creates submissions,
evaluates against the active answer key, and categorizes leads for counsellor outreach.
"""

import csv
import io
import json
from dataclasses import dataclass, field
from fractions import Fraction
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from backend.app.core.grader import QuestionRule, StudentAnswer, grade_paper
from backend.app.core.knowledge_base import (
    get_branch_matrix,
    get_ccmt_cutoffs,
    get_coap_cutoffs,
    get_psu_cutoffs,
)
from backend.app.core.matcher import match_options_for_student
from backend.app.core.normalizer import normalize_gate_score
from backend.app.core.rank_spline import MonotonicRankEngine
from backend.app.db.models import (
    AnswerKeyItemModel,
    AnswerKeyModel,
    EvaluationResultModel,
    QuestionModel,
    StudentResponseModel,
    StudentSubmissionModel,
)


@dataclass
class RowImportError:
    row_number: int
    student_phone: str
    error: str


@dataclass
class BulkImportResult:
    total_rows: int
    successful_count: int
    failed_count: int
    errors: List[Dict[str, Any]] = field(default_factory=list)
    lead_distribution: Dict[str, int] = field(default_factory=dict)
    successful_phones: List[str] = field(default_factory=list)


def parse_csv_or_tsv_content(file_content: str) -> List[Dict[str, str]]:
    """
    Parses CSV, TSV, or semicolon-delimited string into a list of normalized dicts.
    """
    sample = file_content[:2048]
    delimiter = ","
    if "\t" in sample and sample.count("\t") > sample.count(","):
        delimiter = "\t"
    elif ";" in sample and sample.count(";") > sample.count(","):
        delimiter = ";"

    reader = csv.DictReader(io.StringIO(file_content), delimiter=delimiter)
    # Strip whitespace from keys and values
    rows = []
    for r in reader:
        clean_row = {
            (k.strip() if k else ""): (v.strip() if v else "")
            for k, v in r.items()
            if k is not None
        }
        rows.append(clean_row)
    return rows


def process_bulk_import(file_content: str, db: Session) -> BulkImportResult:
    """
    Parses and ingests student records from bulk CSV/TSV content.
    Supports both direct score rows and full Q1..Q65 response rows.
    """
    raw_rows = parse_csv_or_tsv_content(file_content)
    total_rows = len(raw_rows)
    success_count = 0
    fail_count = 0
    errors: List[Dict[str, Any]] = []
    successful_phones: List[str] = []
    lead_dist = {
        "SUPER_TOPPER": 0,
        "PSU_AND_TOP_IIT": 0,
        "NIT_PROSPECT": 0,
        "NURTURE_REPEATER": 0,
    }

    # Preload knowledge base in memory
    coap_data = get_coap_cutoffs()
    ccmt_data = get_ccmt_cutoffs()
    psu_data = get_psu_cutoffs()
    branch_matrix = get_branch_matrix()

    # In-memory caches for batch performance
    rank_engines: Dict[str, MonotonicRankEngine] = {}
    rules_cache: Dict[str, Optional[tuple]] = {}

    for idx, row in enumerate(raw_rows, start=2):  # start=2 considering header line
        phone = row.get("student_phone", row.get("phone", "")).strip()
        name = row.get("student_name", row.get("name", "")).strip()
        paper_code = row.get("paper_code", row.get("branch", "CS")).strip().upper()

        if not phone or len(phone) < 10:
            fail_count += 1
            errors.append({"row_number": idx, "student_phone": phone, "error": "Invalid or missing student_phone"})
            continue

        if not name:
            fail_count += 1
            errors.append({"row_number": idx, "student_phone": phone, "error": "Missing student_name"})
            continue

        category = row.get("student_category", row.get("category", "GEN")).strip().upper()
        if category not in ["GEN", "OBC_NCL", "OBC", "EWS", "SC", "ST", "PWD"]:
            category = "GEN"

        try:
            btech_pct = float(row.get("btech_percentage", row.get("btech_pct", 70.0)))
        except (ValueError, TypeError):
            btech_pct = 70.0

        try:
            cand_age = int(row.get("candidate_age", row.get("age", 23)))
        except (ValueError, TypeError):
            cand_age = 23

        ncl_str = row.get("has_valid_ncl", row.get("ncl", "true")).strip().lower()
        has_ncl = ncl_str in ["true", "1", "yes", "y"]

        batch_id = row.get("pw_batch_id", row.get("batch", "Offline_Drive_2025")).strip()
        session_id = int(row.get("session_id", row.get("shift", 1)) or 1)

        # Deactivate any previous submissions for this student on this paper
        db.query(StudentSubmissionModel).filter(
            StudentSubmissionModel.student_phone == phone,
            StudentSubmissionModel.paper_code == paper_code,
        ).update({"is_active": False})

        # Create submission record
        sub = StudentSubmissionModel(
            student_phone=phone,
            student_name=name,
            student_email=row.get("student_email", row.get("email", None)),
            student_category=category,
            btech_percentage=btech_pct,
            candidate_age=cand_age,
            has_valid_ncl=has_ncl,
            pw_batch_id=batch_id,
            paper_code=paper_code,
            session_id=session_id,
            is_active=True,
        )
        db.add(sub)
        db.flush()

        if paper_code not in rank_engines:
            rank_engines[paper_code] = MonotonicRankEngine(paper_code)
        rank_engine = rank_engines[paper_code]

        # Mode 1: Check if direct score columns exist (raw_score or gate_score)
        raw_score_str = row.get("raw_score", row.get("score", ""))
        gate_score_str = row.get("gate_score", "")

        if raw_score_str or gate_score_str:
            try:
                if raw_score_str:
                    raw_val = float(raw_score_str)
                    norm_res = normalize_gate_score(paper_code, session_id, raw_val, None)
                    gate_sc = norm_res.gate_score
                    norm_marks = norm_res.normalized_marks
                else:
                    gate_sc = int(float(gate_score_str))
                    norm_marks = 50.0  # approximate

                rank_pred = rank_engine.predict_rank(norm_marks)
                rec = match_options_for_student(
                    gate_score=gate_sc,
                    predicted_air=rank_pred.predicted_air,
                    paper_code=paper_code,
                    category=category,
                    btech_percentage=btech_pct,
                    candidate_age=cand_age,
                    has_valid_ncl=has_ncl,
                    historical_coap_data=coap_data,
                    historical_ccmt_data=ccmt_data,
                    historical_psu_data=psu_data,
                    branch_matrix_data=branch_matrix,
                )

                ev = EvaluationResultModel(
                    submission_id=sub.submission_id,
                    key_id=None,
                    raw_score_total=float(raw_score_str or norm_marks),
                    raw_score_aptitude=0.0,
                    raw_score_core=0.0,
                    marks_lost_to_negatives=0.0,
                    correct_count=0,
                    incorrect_count=0,
                    unattempted_count=0,
                    normalized_marks=norm_marks,
                    gate_score=gate_sc,
                    predicted_air=rank_pred.predicted_air,
                    air_range_min=rank_pred.air_range_min,
                    air_range_max=rank_pred.air_range_max,
                    lead_classification=rec.lead_classification,
                )
                db.add(ev)
                success_count += 1
                successful_phones.append(phone)
                lead_dist[rec.lead_classification] = lead_dist.get(rec.lead_classification, 0) + 1
                continue
            except Exception as e:
                db.delete(sub)
                fail_count += 1
                errors.append({"row_number": idx, "student_phone": phone, "error": f"Direct score parsing error: {str(e)}"})
                continue

        # Mode 2: Detailed response evaluation via active answer key
        if paper_code not in rules_cache:
            active_key = (
                db.query(AnswerKeyModel)
                .filter(AnswerKeyModel.paper_code == paper_code, AnswerKeyModel.status == "ACTIVE")
                .order_by(AnswerKeyModel.version.desc())
                .first()
            )

            if not active_key:
                rules_cache[paper_code] = None
            else:
                key_items = db.query(AnswerKeyItemModel).filter(AnswerKeyItemModel.key_id == active_key.key_id).all()
                q_map = {q.question_id: q for q in db.query(QuestionModel).filter(QuestionModel.paper_code == paper_code).all()}

                p_rules = []
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

                    p_rules.append(
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
                rules_cache[paper_code] = (active_key, p_rules)

        cached_entry = rules_cache.get(paper_code)
        if not cached_entry:
            db.delete(sub)
            fail_count += 1
            errors.append({
                "row_number": idx,
                "student_phone": phone,
                "error": f"No active answer key available for paper {paper_code}. Publish key first or provide raw_score.",
            })
            continue

        active_key, rules = cached_entry

        # Extract student answers from Q1..Q65 columns
        student_answers = []
        for r_item in rules:
            q_num = r_item.question_number
            col_key = f"Q{q_num}"
            val = row.get(col_key, row.get(f"q{q_num}", "")).strip()

            stat = "ATTEMPTED" if val and val not in ["--", "NA", "null", "SKIPPED"] else "SKIPPED"
            opts = None
            nat_val = None

            if stat == "ATTEMPTED":
                if r_item.question_type == "NAT":
                    nat_val = val
                else:
                    opts = [o.strip().upper() for o in val.replace(";", ",").split(",") if o.strip().upper() in ["A", "B", "C", "D"]]
                    if not opts:
                        stat = "SKIPPED"

            # Create DB response record
            db_resp = StudentResponseModel(
                submission_id=sub.submission_id,
                question_id=r_item.question_id,
                status=stat,
                student_options_json=json.dumps(opts) if opts else None,
                student_nat_value=nat_val,
            )
            db.add(db_resp)

            student_answers.append(
                StudentAnswer(
                    question_id=r_item.question_id,
                    status=stat,
                    marked_options=opts,
                    nat_value=nat_val,
                )
            )

        summary = grade_paper(rules, student_answers)
        norm_result = normalize_gate_score(paper_code, session_id, summary.total_raw_score, None)
        rank_pred = rank_engine.predict_rank(norm_result.normalized_marks)
        rec_summary = match_options_for_student(
            gate_score=norm_result.gate_score,
            predicted_air=rank_pred.predicted_air,
            paper_code=paper_code,
            category=category,
            btech_percentage=btech_pct,
            candidate_age=cand_age,
            has_valid_ncl=has_ncl,
            historical_coap_data=coap_data,
            historical_ccmt_data=ccmt_data,
            historical_psu_data=psu_data,
            branch_matrix_data=branch_matrix,
        )

        eval_rec = EvaluationResultModel(
            submission_id=sub.submission_id,
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
        db.add(eval_rec)
        success_count += 1
        successful_phones.append(phone)
        lead_dist[rec_summary.lead_classification] = lead_dist.get(rec_summary.lead_classification, 0) + 1

    db.commit()

    return BulkImportResult(
        total_rows=total_rows,
        successful_count=success_count,
        failed_count=fail_count,
        errors=errors,
        lead_distribution=lead_dist,
        successful_phones=successful_phones,
    )
