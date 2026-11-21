"""
Deterministic Grading Engine for GATE Examination
Supports MCQ, MSQ, NAT, and MTA (Marks to All) rules.
Uses exact fractional arithmetic (fractions.Fraction) to prevent floating-point drift.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import re
from typing import Dict, List, Optional, Set, Union


NAT_REGEX = re.compile(r"^[-+]?(?:\d*\.?\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?$")


@dataclass(frozen=True)
class QuestionRule:
    question_id: str
    question_number: int
    question_type: str  # "MCQ", "MSQ", "NAT"
    section: str  # "APTITUDE" or "CORE"
    marks_correct: Fraction  # Fraction(1, 1) or Fraction(2, 1)
    marks_negative: Fraction  # Fraction(1, 3), Fraction(2, 3), or Fraction(0, 1)
    is_mta: bool = False
    valid_mcq_options: Optional[List[str]] = None  # e.g., ["A"] or ["A", "B"] if multiple accepted
    valid_msq_sets: Optional[List[Set[str]]] = None  # e.g., [{"A", "C"}]
    nat_min: Optional[Decimal] = None
    nat_max: Optional[Decimal] = None


@dataclass
class StudentAnswer:
    question_id: str
    status: str  # "ATTEMPTED", "SKIPPED", "MARKED_FOR_REVIEW"
    marked_options: Optional[List[str]] = None  # e.g., ["A"] or ["A", "B"]
    nat_value: Optional[str] = None  # raw string entered by student


@dataclass
class QuestionGradingResult:
    question_id: str
    question_number: int
    question_type: str
    section: str
    is_correct: bool
    is_negative: bool
    is_mta: bool
    is_attempted: bool
    marks_awarded: float
    marks_awarded_fraction: Fraction
    marks_lost: float  # positive number representing penalty surrendered


@dataclass
class PaperGradingSummary:
    total_raw_score: float
    aptitude_score: float
    core_score: float
    marks_lost_to_negatives: float
    correct_count: int
    incorrect_count: int
    unattempted_count: int
    mta_count: int
    question_results: List[QuestionGradingResult]


def clean_nat_string(raw: Optional[str]) -> Optional[Decimal]:
    """
    Sanitizes candidate NAT input:
    - Strips whitespace
    - Replaces international comma decimals with period
    - Validates regex for float/scientific notation
    - Converts to exact Decimal
    """
    if raw is None:
        return None
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    if not cleaned:
        return None
    if not NAT_REGEX.match(cleaned):
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def grade_question(rule: QuestionRule, answer: Optional[StudentAnswer]) -> QuestionGradingResult:
    """
    Grades an individual question deterministically using exact rational fractions.
    """
    # 1. Marks to All (MTA) check
    # Official GATE Rule: When a question is dropped / MTA, full marks are awarded to ALL candidates
    if rule.is_mta:
        return QuestionGradingResult(
            question_id=rule.question_id,
            question_number=rule.question_number,
            question_type=rule.question_type,
            section=rule.section,
            is_correct=True,
            is_negative=False,
            is_mta=True,
            is_attempted=answer.status == "ATTEMPTED" if answer else False,
            marks_awarded=float(rule.marks_correct),
            marks_awarded_fraction=rule.marks_correct,
            marks_lost=0.0,
        )

    # 2. Check if attempted
    if not answer or answer.status == "SKIPPED":
        return QuestionGradingResult(
            question_id=rule.question_id,
            question_number=rule.question_number,
            question_type=rule.question_type,
            section=rule.section,
            is_correct=False,
            is_negative=False,
            is_mta=False,
            is_attempted=False,
            marks_awarded=0.0,
            marks_awarded_fraction=Fraction(0, 1),
            marks_lost=0.0,
        )

    # 3. Evaluate by Question Type
    q_type = rule.question_type.upper()

    if q_type == "MCQ":
        # Candidate must choose 1 option
        chosen = answer.marked_options[0].upper().strip() if answer.marked_options else ""
        if not chosen:
            # Marked attempted but no option
            return QuestionGradingResult(
                question_id=rule.question_id,
                question_number=rule.question_number,
                question_type=rule.question_type,
                section=rule.section,
                is_correct=False,
                is_negative=False,
                is_mta=False,
                is_attempted=False,
                marks_awarded=0.0,
                marks_awarded_fraction=Fraction(0, 1),
                marks_lost=0.0,
            )

        valid_keys = [k.upper().strip() for k in (rule.valid_mcq_options or [])]
        if chosen in valid_keys:
            return QuestionGradingResult(
                question_id=rule.question_id,
                question_number=rule.question_number,
                question_type=rule.question_type,
                section=rule.section,
                is_correct=True,
                is_negative=False,
                is_mta=False,
                is_attempted=True,
                marks_awarded=float(rule.marks_correct),
                marks_awarded_fraction=rule.marks_correct,
                marks_lost=0.0,
            )
        else:
            # Incorrect MCQ: Negative marking applies
            penalty = rule.marks_negative
            return QuestionGradingResult(
                question_id=rule.question_id,
                question_number=rule.question_number,
                question_type=rule.question_type,
                section=rule.section,
                is_correct=False,
                is_negative=True,
                is_mta=False,
                is_attempted=True,
                marks_awarded=-float(penalty),
                marks_awarded_fraction=-penalty,
                marks_lost=float(penalty),
            )

    elif q_type == "MSQ":
        # Candidate marks multi-select checkboxes
        chosen_set = {opt.upper().strip() for opt in (answer.marked_options or []) if opt.strip()}
        if not chosen_set:
            return QuestionGradingResult(
                question_id=rule.question_id,
                question_number=rule.question_number,
                question_type=rule.question_type,
                section=rule.section,
                is_correct=False,
                is_negative=False,
                is_mta=False,
                is_attempted=False,
                marks_awarded=0.0,
                marks_awarded_fraction=Fraction(0, 1),
                marks_lost=0.0,
            )

        valid_sets = [{opt.upper().strip() for opt in s} for s in (rule.valid_msq_sets or [])]
        # Strictly zero partial marking in GATE
        if chosen_set in valid_sets:
            return QuestionGradingResult(
                question_id=rule.question_id,
                question_number=rule.question_number,
                question_type=rule.question_type,
                section=rule.section,
                is_correct=True,
                is_negative=False,
                is_mta=False,
                is_attempted=True,
                marks_awarded=float(rule.marks_correct),
                marks_awarded_fraction=rule.marks_correct,
                marks_lost=0.0,
            )
        else:
            # In MSQ, wrong answer gets 0.0 marks (NO negative marking)
            return QuestionGradingResult(
                question_id=rule.question_id,
                question_number=rule.question_number,
                question_type=rule.question_type,
                section=rule.section,
                is_correct=False,
                is_negative=False,
                is_mta=False,
                is_attempted=True,
                marks_awarded=0.0,
                marks_awarded_fraction=Fraction(0, 1),
                marks_lost=0.0,
            )

    elif q_type == "NAT":
        clean_val = clean_nat_string(answer.nat_value)
        if clean_val is None:
            return QuestionGradingResult(
                question_id=rule.question_id,
                question_number=rule.question_number,
                question_type=rule.question_type,
                section=rule.section,
                is_correct=False,
                is_negative=False,
                is_mta=False,
                is_attempted=False,
                marks_awarded=0.0,
                marks_awarded_fraction=Fraction(0, 1),
                marks_lost=0.0,
            )

        # Range verification: nat_min <= clean_val <= nat_max with small numerical tolerance
        tolerance = Decimal("0.00001")
        is_in_range = False
        if rule.nat_min is not None and rule.nat_max is not None:
            is_in_range = (rule.nat_min - tolerance) <= clean_val <= (rule.nat_max + tolerance)

        if is_in_range:
            return QuestionGradingResult(
                question_id=rule.question_id,
                question_number=rule.question_number,
                question_type=rule.question_type,
                section=rule.section,
                is_correct=True,
                is_negative=False,
                is_mta=False,
                is_attempted=True,
                marks_awarded=float(rule.marks_correct),
                marks_awarded_fraction=rule.marks_correct,
                marks_lost=0.0,
            )
        else:
            # In NAT, wrong answer gets 0.0 marks (NO negative marking)
            return QuestionGradingResult(
                question_id=rule.question_id,
                question_number=rule.question_number,
                question_type=rule.question_type,
                section=rule.section,
                is_correct=False,
                is_negative=False,
                is_mta=False,
                is_attempted=True,
                marks_awarded=0.0,
                marks_awarded_fraction=Fraction(0, 1),
                marks_lost=0.0,
            )

    raise ValueError(f"Unknown question type: {rule.question_type}")


def grade_paper(
    rules: List[QuestionRule], answers: List[StudentAnswer]
) -> PaperGradingSummary:
    """
    Evaluates an entire candidate paper.
    Calculates total score, section breakdown, and marks lost to negatives.
    """
    answer_map = {ans.question_id: ans for ans in answers}
    results: List[QuestionGradingResult] = []

    total_frac = Fraction(0, 1)
    aptitude_frac = Fraction(0, 1)
    core_frac = Fraction(0, 1)
    lost_frac = Fraction(0, 1)

    correct_count = 0
    incorrect_count = 0
    unattempted_count = 0
    mta_count = 0

    for rule in rules:
        ans = answer_map.get(rule.question_id)
        res = grade_question(rule, ans)
        results.append(res)

        total_frac += res.marks_awarded_fraction

        if rule.section.upper() == "APTITUDE":
            aptitude_frac += res.marks_awarded_fraction
        else:
            core_frac += res.marks_awarded_fraction

        if res.is_negative:
            lost_frac += Fraction(Decimal(str(res.marks_lost)))

        if res.is_mta:
            mta_count += 1
            correct_count += 1
        elif res.is_correct:
            correct_count += 1
        elif res.is_attempted:
            incorrect_count += 1
        else:
            unattempted_count += 1

    return PaperGradingSummary(
        total_raw_score=round(float(total_frac), 4),
        aptitude_score=round(float(aptitude_frac), 4),
        core_score=round(float(core_frac), 4),
        marks_lost_to_negatives=round(float(lost_frac), 4),
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        unattempted_count=unattempted_count,
        mta_count=mta_count,
        question_results=results,
    )
