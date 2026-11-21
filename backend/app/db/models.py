"""
SQLAlchemy Declarative Models for Exam Papers, Questions, Versioned Keys,
Student Submissions, Evaluations, and Predictions.
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from backend.app.db.session import Base


def generate_uuid() -> str:
    return str(uuid.uuid4())


class PaperModel(Base):
    __tablename__ = "papers"

    paper_code = Column(String(10), primary_key=True)  # e.g., "CS", "ME"
    year = Column(Integer, nullable=False, default=2025)
    total_questions = Column(Integer, default=65)
    total_marks = Column(Integer, default=100)
    is_multi_session = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    questions = relationship("QuestionModel", back_populates="paper", cascade="all, delete-orphan")
    answer_keys = relationship("AnswerKeyModel", back_populates="paper", cascade="all, delete-orphan")
    submissions = relationship("StudentSubmissionModel", back_populates="paper")


class QuestionModel(Base):
    __tablename__ = "questions"

    question_id = Column(String(64), primary_key=True, default=generate_uuid)
    paper_code = Column(String(10), ForeignKey("papers.paper_code"), nullable=False)
    question_number = Column(Integer, nullable=False)  # 1 to 65
    section = Column(String(20), nullable=False)  # "APTITUDE" or "CORE"
    question_type = Column(String(10), nullable=False)  # "MCQ", "MSQ", "NAT"
    marks_correct = Column(Float, nullable=False, default=1.0)
    marks_negative = Column(Float, nullable=False, default=0.3333)
    subject_tag = Column(String(64), nullable=True)

    paper = relationship("PaperModel", back_populates="questions")
    key_items = relationship("AnswerKeyItemModel", back_populates="question")


class AnswerKeyModel(Base):
    __tablename__ = "answer_keys"

    key_id = Column(String(64), primary_key=True, default=generate_uuid)
    paper_code = Column(String(10), ForeignKey("papers.paper_code"), nullable=False)
    version = Column(Integer, nullable=False, default=1)
    key_type = Column(String(32), nullable=False)  # "FACULTY_EXAM_DAY", "OFFICIAL_IIT"
    author_name = Column(String(64), default="PW Faculty Panel")
    status = Column(String(20), default="ACTIVE")  # "ACTIVE", "DRAFT", "ARCHIVED"
    published_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    paper = relationship("PaperModel", back_populates="answer_keys")
    items = relationship("AnswerKeyItemModel", back_populates="answer_key", cascade="all, delete-orphan")
    evaluations = relationship("EvaluationResultModel", back_populates="answer_key")


class AnswerKeyItemModel(Base):
    __tablename__ = "answer_key_items"

    item_id = Column(String(64), primary_key=True, default=generate_uuid)
    key_id = Column(String(64), ForeignKey("answer_keys.key_id"), nullable=False)
    question_id = Column(String(64), ForeignKey("questions.question_id"), nullable=False)
    is_mta = Column(Boolean, default=False)
    valid_options_json = Column(Text, nullable=True)  # JSON e.g. [["A"], ["B"]]
    nat_min = Column(Numeric(12, 4), nullable=True)
    nat_max = Column(Numeric(12, 4), nullable=True)

    answer_key = relationship("AnswerKeyModel", back_populates="items")
    question = relationship("QuestionModel", back_populates="key_items")


class StudentSubmissionModel(Base):
    __tablename__ = "student_submissions"

    submission_id = Column(String(64), primary_key=True, default=generate_uuid)
    student_phone = Column(String(15), nullable=False, index=True)
    student_name = Column(String(64), nullable=False)
    student_email = Column(String(64), nullable=True)
    student_category = Column(String(20), default="GEN")
    btech_percentage = Column(Float, default=70.0)
    candidate_age = Column(Integer, default=22)
    has_valid_ncl = Column(Boolean, default=True)
    pw_batch_id = Column(String(64), nullable=True)
    paper_code = Column(String(10), ForeignKey("papers.paper_code"), nullable=False)
    session_id = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    paper = relationship("PaperModel", back_populates="submissions")
    responses = relationship("StudentResponseModel", back_populates="submission", cascade="all, delete-orphan")
    evaluation = relationship("EvaluationResultModel", back_populates="submission", uselist=False, cascade="all, delete-orphan")


class StudentResponseModel(Base):
    __tablename__ = "student_responses"

    response_id = Column(String(64), primary_key=True, default=generate_uuid)
    submission_id = Column(String(64), ForeignKey("student_submissions.submission_id"), nullable=False)
    question_id = Column(String(64), ForeignKey("questions.question_id"), nullable=False)
    status = Column(String(20), default="ATTEMPTED")  # "ATTEMPTED", "SKIPPED"
    student_options_json = Column(Text, nullable=True)  # JSON list e.g. ["A", "C"]
    student_nat_value = Column(String(32), nullable=True)

    submission = relationship("StudentSubmissionModel", back_populates="responses")


class EvaluationResultModel(Base):
    __tablename__ = "evaluation_results"

    eval_id = Column(String(64), primary_key=True, default=generate_uuid)
    submission_id = Column(String(64), ForeignKey("student_submissions.submission_id"), nullable=False, unique=True)
    key_id = Column(String(64), ForeignKey("answer_keys.key_id"), nullable=False)
    raw_score_total = Column(Float, nullable=False)
    raw_score_aptitude = Column(Float, nullable=False)
    raw_score_core = Column(Float, nullable=False)
    marks_lost_to_negatives = Column(Float, nullable=False)
    correct_count = Column(Integer, default=0)
    incorrect_count = Column(Integer, default=0)
    unattempted_count = Column(Integer, default=0)
    normalized_marks = Column(Float, nullable=False)
    gate_score = Column(Integer, nullable=False)
    predicted_air = Column(Integer, nullable=False)
    air_range_min = Column(Integer, nullable=False)
    air_range_max = Column(Integer, nullable=False)
    lead_classification = Column(String(32), default="NIT_PROSPECT")
    evaluated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    submission = relationship("StudentSubmissionModel", back_populates="evaluation")
    answer_key = relationship("AnswerKeyModel", back_populates="evaluations")
