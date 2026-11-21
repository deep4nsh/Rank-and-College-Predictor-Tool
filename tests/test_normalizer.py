import numpy as np
import pytest
from backend.app.core.normalizer import (
    calculate_gate_score,
    normalize_gate_score,
    scrub_outliers_iqr,
)


def test_outlier_scrubbing():
    # 50 normal scores around 35-65, with 2 extreme trolls (100.0 and 0.0)
    np.random.seed(42)
    scores = list(np.random.normal(loc=50.0, scale=8.0, size=50))
    scores.append(150.0)  # Extreme malicious outlier
    scores.append(-40.0)  # Extreme malicious outlier

    cleaned = scrub_outliers_iqr(scores)
    assert 150.0 not in cleaned
    assert -40.0 not in cleaned
    assert len(cleaned) >= 45


def test_single_session_paper_bypass():
    # Data Science (DA) is a single-session paper
    res = normalize_gate_score(
        paper_code="DA",
        session_id=1,
        raw_score=72.5,
        all_sessions_scores=None,
    )
    assert res.is_multi_session is False
    assert res.normalized_marks == 72.5
    assert res.gate_score >= 700


def test_multi_session_small_sample_fallback():
    # Only 10 submissions in session 1 (below min_sample_size=50)
    scores = {1: [60.0] * 10, 2: [60.0] * 10}
    res = normalize_gate_score(
        paper_code="CS",
        session_id=1,
        raw_score=65.0,
        all_sessions_scores=scores,
        min_sample_size=50,
    )
    # Should safely fallback to raw score without crashing
    assert res.normalized_marks == 65.0
    assert res.sample_size_used == 10


def test_multi_session_normalization_mechanics():
    # Session 1: Tough paper (mean ~40)
    # Session 2: Easy paper (mean ~55)
    np.random.seed(42)
    s1_scores = list(np.random.normal(loc=40.0, scale=10.0, size=200))
    s2_scores = list(np.random.normal(loc=55.0, scale=12.0, size=200))

    all_scores = {1: s1_scores, 2: s2_scores}

    # Student A scored 60 in the tough session 1
    res_s1 = normalize_gate_score(
        paper_code="CS",
        session_id=1,
        raw_score=60.0,
        all_sessions_scores=all_scores,
    )

    # Student B scored 60 in the easy session 2
    res_s2 = normalize_gate_score(
        paper_code="CS",
        session_id=2,
        raw_score=60.0,
        all_sessions_scores=all_scores,
    )

    # Normalization should reward the candidate from the tougher session
    assert res_s1.normalized_marks > res_s2.normalized_marks
    assert res_s1.gate_score > res_s2.gate_score


def test_gate_score_bounds():
    assert calculate_gate_score(10.0, qualifying_marks=28.0) >= 100
    assert calculate_gate_score(98.0, qualifying_marks=28.0, top_01_marks=90.0) <= 1000
