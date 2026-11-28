"""
Official GATE 2026 Question Papers & Answer Keys Loader (IIT Guwahati).
Loads all 10 authentic GATE 2026 papers and official final answer keys from
data/gate2026_papers.json:
- CS (Session 1 & Session 2)
- CE (Session 1 & Session 2)
- DA (Session 1)
- ME (Session 1)
- EE (Session 1)
- EC (Session 1)
- IN (Session 1)
- CH (Session 1)
"""

from functools import lru_cache
import json
import os
from typing import Any, Dict
from sqlalchemy.orm import Session

from backend.app.db.models import (
    AnswerKeyItemModel,
    AnswerKeyModel,
    PaperModel,
    QuestionModel,
)

DATA_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "gate2026_papers.json")
)

MULTI_SESSION_PAPERS_2026 = {"CS", "CE"}


@lru_cache(maxsize=1)
def _load_gate2026_papers() -> Dict[str, Any]:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_sample_paper(paper_code: str, session_id: int = 1) -> Dict[str, Any]:
    """
    Returns the authentic GATE 2026 65-question paper and official answer key
    for the requested paper_code and session_id.
    """
    clean_paper = paper_code.upper().strip()
    session = int(session_id) if session_id in (1, 2) else 1
    if clean_paper not in MULTI_SESSION_PAPERS_2026:
        session = 1

    papers = _load_gate2026_papers()
    key = f"{clean_paper}_S{session}"
    if key not in papers:
        # Fallback to session 1 if requested session doesn't exist
        key = f"{clean_paper}_S1"
    if key not in papers:
        raise ValueError(f"Official GATE 2026 paper not found for {clean_paper} Session {session}")

    raw_paper = papers[key]
    full_questions = []
    for q in raw_paper["questions"]:
        q_copy = dict(q)
        q_copy["question_id"] = f"{clean_paper}-S{session}-Q{q_copy['question_number']}"
        full_questions.append(q_copy)

    return {
        "paper_code": clean_paper,
        "session_id": session,
        "session_name": f"Session {session} ({'Forenoon' if session == 1 else 'Afternoon'})",
        "year": 2026,
        "official_qp_url": raw_paper.get("official_qp_url"),
        "official_key_url": raw_paper.get("official_key_url"),
        "total_questions": len(full_questions),
        "total_marks": 100,
        "duration_minutes": 180,
        "questions": full_questions,
    }


def sync_sample_paper_to_db(db: Session, paper_code: str, session_id: int = 1) -> Dict[str, Any]:
    """
    Ensures that the official GATE 2026 Paper, 65 Questions, and active Official IIT
    Answer Key exist in the database for the given paper_code and session_id.
    """
    clean_paper = paper_code.upper().strip()
    paper_data = get_sample_paper(clean_paper, session_id)

    # 1. Ensure PaperModel exists
    existing_paper = db.query(PaperModel).filter(PaperModel.paper_code == clean_paper).first()
    if not existing_paper:
        existing_paper = PaperModel(
            paper_code=clean_paper,
            year=2026,
            total_questions=65,
            total_marks=100,
            is_multi_session=(clean_paper in MULTI_SESSION_PAPERS_2026),
        )
        db.add(existing_paper)
        db.flush()

    # 2. Ensure QuestionModel records exist
    existing_qids = {
        q[0] for q in db.query(QuestionModel.question_id).filter(QuestionModel.paper_code == clean_paper).all()
    }

    new_q_models = []
    for q in paper_data["questions"]:
        qid = q["question_id"]
        if qid not in existing_qids:
            new_q = QuestionModel(
                question_id=qid,
                paper_code=clean_paper,
                question_number=q["question_number"],
                section=q["section"],
                question_type=q["question_type"],
                marks_correct=float(q["marks_correct"]),
                marks_negative=float(q["marks_negative"]),
                subject_tag=q.get("subject_tag"),
            )
            db.add(new_q)
            new_q_models.append(new_q)
            existing_qids.add(qid)

    if new_q_models:
        db.flush()

    # 3. Ensure an active AnswerKeyModel exists with items for all questions
    active_key = (
        db.query(AnswerKeyModel)
        .filter(AnswerKeyModel.paper_code == clean_paper, AnswerKeyModel.status == "ACTIVE")
        .order_by(AnswerKeyModel.version.desc())
        .first()
    )

    if not active_key:
        active_key = AnswerKeyModel(
            paper_code=clean_paper,
            version=1,
            key_type="OFFICIAL_IIT",
            author_name="IIT Guwahati (GATE 2026 Official Key)",
            status="ACTIVE",
        )
        db.add(active_key)
        db.flush()

    existing_item_qids = {
        item.question_id
        for item in db.query(AnswerKeyItemModel.question_id).filter(AnswerKeyItemModel.key_id == active_key.key_id).all()
    }

    new_items = []
    for q in paper_data["questions"]:
        qid = q["question_id"]
        if qid not in existing_item_qids:
            valid_opts = None
            if q.get("correct_options"):
                if q["question_type"] == "MCQ":
                    valid_opts = json.dumps([[opt] for opt in q["correct_options"]])
                else:
                    valid_opts = json.dumps([q["correct_options"]])

            item = AnswerKeyItemModel(
                key_id=active_key.key_id,
                question_id=qid,
                is_mta=bool(q.get("is_mta", False)),
                valid_options_json=valid_opts,
                nat_min=q.get("nat_min"),
                nat_max=q.get("nat_max"),
            )
            db.add(item)
            new_items.append(item)
            existing_item_qids.add(qid)

    if new_items or new_q_models:
        db.flush()
        db.commit()

    return paper_data
