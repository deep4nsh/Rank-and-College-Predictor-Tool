from decimal import Decimal
from fractions import Fraction
import pytest
from backend.app.core.grader import (
    PaperGradingSummary,
    QuestionGradingResult,
    QuestionRule,
    StudentAnswer,
    clean_nat_string,
    grade_paper,
    grade_question,
)


def test_nat_string_sanitization():
    assert clean_nat_string(" 12.5 ") == Decimal("12.5")
    assert clean_nat_string("12,5") == Decimal("12.5")
    assert clean_nat_string("003.140") == Decimal("3.140")
    assert clean_nat_string("-0.5") == Decimal("-0.5")
    assert clean_nat_string("-.5") == Decimal("-0.5")
    assert clean_nat_string("1.5e-3") == Decimal("0.0015")
    assert clean_nat_string("invalid_abc") is None
    assert clean_nat_string("") is None
    assert clean_nat_string(None) is None


def test_mcq_1_mark():
    rule = QuestionRule(
        question_id="Q1",
        question_number=1,
        question_type="MCQ",
        section="APTITUDE",
        marks_correct=Fraction(1, 1),
        marks_negative=Fraction(1, 3),
        valid_mcq_options=["B"],
    )

    # Correct
    ans_correct = StudentAnswer(question_id="Q1", status="ATTEMPTED", marked_options=["B"])
    res = grade_question(rule, ans_correct)
    assert res.is_correct is True
    assert res.marks_awarded == 1.0
    assert res.marks_lost == 0.0

    # Incorrect
    ans_wrong = StudentAnswer(question_id="Q1", status="ATTEMPTED", marked_options=["C"])
    res = grade_question(rule, ans_wrong)
    assert res.is_correct is False
    assert res.is_negative is True
    assert res.marks_awarded == pytest.approx(-1 / 3)
    assert res.marks_lost == pytest.approx(1 / 3)

    # Skipped
    ans_skipped = StudentAnswer(question_id="Q1", status="SKIPPED")
    res = grade_question(rule, ans_skipped)
    assert res.is_correct is False
    assert res.marks_awarded == 0.0
    assert res.marks_lost == 0.0


def test_mcq_multiple_valid_keys():
    rule = QuestionRule(
        question_id="Q2",
        question_number=2,
        question_type="MCQ",
        section="CORE",
        marks_correct=Fraction(2, 1),
        marks_negative=Fraction(2, 3),
        valid_mcq_options=["A", "C"],  # IIT accepted A OR C
    )

    res_a = grade_question(rule, StudentAnswer("Q2", "ATTEMPTED", marked_options=["A"]))
    assert res_a.is_correct is True
    assert res_a.marks_awarded == 2.0

    res_c = grade_question(rule, StudentAnswer("Q2", "ATTEMPTED", marked_options=["C"]))
    assert res_c.is_correct is True
    assert res_c.marks_awarded == 2.0

    res_b = grade_question(rule, StudentAnswer("Q2", "ATTEMPTED", marked_options=["B"]))
    assert res_b.is_correct is False
    assert res_b.marks_awarded == pytest.approx(-2 / 3)


def test_msq_strict_zero_partial_marking():
    rule = QuestionRule(
        question_id="Q3",
        question_number=3,
        question_type="MSQ",
        section="CORE",
        marks_correct=Fraction(2, 1),
        marks_negative=Fraction(0, 1),
        valid_msq_sets=[{"A", "B", "C"}],
    )

    # Exact match -> Full Marks
    res_full = grade_question(rule, StudentAnswer("Q3", "ATTEMPTED", marked_options=["C", "A", "B"]))
    assert res_full.is_correct is True
    assert res_full.marks_awarded == 2.0

    # Partial selection {A, B} -> STRICTLY ZERO (No partial marking in GATE)
    res_partial = grade_question(rule, StudentAnswer("Q3", "ATTEMPTED", marked_options=["A", "B"]))
    assert res_partial.is_correct is False
    assert res_partial.marks_awarded == 0.0
    assert res_partial.marks_lost == 0.0

    # Over-selection {A, B, C, D} -> STRICTLY ZERO
    res_over = grade_question(rule, StudentAnswer("Q3", "ATTEMPTED", marked_options=["A", "B", "C", "D"]))
    assert res_over.is_correct is False
    assert res_over.marks_awarded == 0.0


def test_nat_range_and_zeros():
    rule = QuestionRule(
        question_id="Q4",
        question_number=4,
        question_type="NAT",
        section="CORE",
        marks_correct=Fraction(2, 1),
        marks_negative=Fraction(0, 1),
        nat_min=Decimal("3.14"),
        nat_max=Decimal("3.15"),
    )

    # Within range
    res1 = grade_question(rule, StudentAnswer("Q4", "ATTEMPTED", nat_value="3.142"))
    assert res1.is_correct is True
    assert res1.marks_awarded == 2.0

    # Exact boundary with trailing zeros
    res2 = grade_question(rule, StudentAnswer("Q4", "ATTEMPTED", nat_value="03.1400"))
    assert res2.is_correct is True
    assert res2.marks_awarded == 2.0

    # Outside range -> 0 marks, 0 negative
    res3 = grade_question(rule, StudentAnswer("Q4", "ATTEMPTED", nat_value="3.16"))
    assert res3.is_correct is False
    assert res3.marks_awarded == 0.0
    assert res3.marks_lost == 0.0


def test_mta_marks_to_all():
    rule = QuestionRule(
        question_id="Q5",
        question_number=5,
        question_type="MCQ",
        section="CORE",
        marks_correct=Fraction(2, 1),
        marks_negative=Fraction(2, 3),
        is_mta=True,
    )

    # Candidate who skipped MUST get full marks under GATE MTA rule
    res_skipped = grade_question(rule, StudentAnswer("Q5", "SKIPPED"))
    assert res_skipped.is_correct is True
    assert res_skipped.is_mta is True
    assert res_skipped.marks_awarded == 2.0

    # Candidate who answered wrong MUST also get full marks under GATE MTA rule
    res_wrong = grade_question(rule, StudentAnswer("Q5", "ATTEMPTED", marked_options=["D"]))
    assert res_wrong.is_correct is True
    assert res_wrong.marks_awarded == 2.0


def test_full_paper_evaluation():
    rules = [
        QuestionRule("Q1", 1, "MCQ", "APTITUDE", Fraction(1, 1), Fraction(1, 3), valid_mcq_options=["A"]),
        QuestionRule("Q2", 2, "MCQ", "APTITUDE", Fraction(2, 1), Fraction(2, 3), valid_mcq_options=["B"]),
        QuestionRule("Q3", 3, "MSQ", "CORE", Fraction(2, 1), Fraction(0, 1), valid_msq_sets=[{"A", "C"}]),
        QuestionRule("Q4", 4, "NAT", "CORE", Fraction(2, 1), Fraction(0, 1), nat_min=Decimal("10.0"), nat_max=Decimal("10.5")),
        QuestionRule("Q5", 5, "MCQ", "CORE", Fraction(2, 1), Fraction(2, 3), is_mta=True),
    ]

    answers = [
        StudentAnswer("Q1", "ATTEMPTED", marked_options=["A"]),  # +1.0
        StudentAnswer("Q2", "ATTEMPTED", marked_options=["C"]),  # -0.6667
        StudentAnswer("Q3", "ATTEMPTED", marked_options=["A", "C"]),  # +2.0
        StudentAnswer("Q4", "SKIPPED"),  # 0.0
        StudentAnswer("Q5", "SKIPPED"),  # +2.0 (MTA)
    ]

    summary = grade_paper(rules, answers)

    # Net total: 1.0 - (2/3) + 2.0 + 0 + 2.0 = 5.0 - 0.6666666666666666 = 4.3333
    assert summary.total_raw_score == pytest.approx(4.3333, abs=0.001)
    assert summary.aptitude_score == pytest.approx(0.3333, abs=0.001)
    assert summary.core_score == pytest.approx(4.0, abs=0.001)
    assert summary.marks_lost_to_negatives == pytest.approx(2 / 3, abs=0.001)
    assert summary.correct_count == 3
    assert summary.incorrect_count == 1
    assert summary.unattempted_count == 1
    assert summary.mta_count == 1
