import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.db.models import AnswerKeyItemModel, AnswerKeyModel, PaperModel
from backend.app.db.session import get_db
from backend.app.schemas.key import AnswerKeyCreateSchema

router = APIRouter(prefix="/keys", tags=["Answer Keys"])


@router.post("")
def create_answer_key(payload: AnswerKeyCreateSchema, db: Session = Depends(get_db)):
    """
    Creates and publishes an answer key (PW Faculty or Official IIT).
    """
    # Verify paper exists
    paper = db.query(PaperModel).filter(PaperModel.paper_code == payload.paper_code.upper()).first()
    if not paper:
        # Auto-create paper if not present
        paper = PaperModel(paper_code=payload.paper_code.upper(), year=2025)
        db.add(paper)
        db.commit()

    # Create key
    new_key = AnswerKeyModel(
        paper_code=payload.paper_code.upper(),
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
        .filter(AnswerKeyModel.paper_code == paper_code.upper(), AnswerKeyModel.status == "ACTIVE")
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
