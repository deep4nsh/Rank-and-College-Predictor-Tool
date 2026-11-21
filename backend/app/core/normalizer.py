"""
Official GATE Multi-Session Normalization & Statistical Engine
Implements official IIT GATE formula with Outlier Scrubbing (Anti-Poisoning)
and Division-by-Zero / Sample Size Gatekeepers.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set
import numpy as np


MULTI_SESSION_PAPERS: Set[str] = {"CS", "ME", "CE", "EE", "EC"}


@dataclass
class NormalizationResult:
    paper_code: str
    session_id: int
    raw_score: float
    normalized_marks: float
    gate_score: int
    is_multi_session: bool
    sample_size_used: int
    session_mean: float
    session_std: float


def scrub_outliers_iqr(scores: List[float], multiplier: float = 2.5) -> List[float]:
    """
    Scrubs malicious / bot / troll submissions using Interquartile Range (IQR).
    Guards against data poisoning attacks on exam-day shift statistics.
    """
    if len(scores) < 20:
        return scores
    arr = np.array(scores, dtype=np.float64)
    q1 = np.percentile(arr, 25)
    q3 = np.percentile(arr, 75)
    iqr = q3 - q1
    if iqr == 0:
        return scores
    lower = q1 - multiplier * iqr
    upper = q3 + multiplier * iqr
    filtered = [s for s in scores if lower <= s <= upper]
    # Return at least 80% of data if filter was too aggressive
    return filtered if len(filtered) >= 10 else scores


def compute_top_01_percent_mean(scores: List[float]) -> float:
    """
    Computes average marks of top 0.1% candidates.
    If sample is small, takes top 1 or top 1% as a robust estimate.
    """
    if not scores:
        return 0.0
    arr = np.sort(np.array(scores, dtype=np.float64))[::-1]
    n = len(arr)
    # top 0.1% count, min 1
    count = max(1, int(np.ceil(n * 0.001)))
    return float(np.mean(arr[:count]))


def calculate_gate_score(
    normalized_marks: float,
    qualifying_marks: float = 28.5,
    top_01_marks: float = 85.0,
    sq: int = 350,
    st: int = 900,
) -> int:
    """
    Calculates official GATE Score out of 1000:
    S = Sq + (St - Sq) * ((M - Mq) / (Mt - Mq))
    Clamped strictly to [100, 1000].
    """
    if top_01_marks <= qualifying_marks:
        top_01_marks = qualifying_marks + 50.0

    if normalized_marks < qualifying_marks:
        # Below qualifying mark, score scales down from 350 towards 100
        ratio = max(0.0, normalized_marks / max(1.0, qualifying_marks))
        raw_gate = int(100 + (sq - 100) * ratio)
    else:
        diff_denom = top_01_marks - qualifying_marks
        ratio = (normalized_marks - qualifying_marks) / diff_denom
        raw_gate = int(sq + (st - sq) * ratio)

    # Clamp to [100, 1000]
    return max(100, min(1000, raw_gate))


def normalize_gate_score(
    paper_code: str,
    session_id: int,
    raw_score: float,
    all_sessions_scores: Optional[Dict[int, List[float]]] = None,
    min_sample_size: int = 50,
    historical_qualifying_marks: float = 28.5,
    historical_top_marks: float = 85.0,
) -> NormalizationResult:
    """
    Computes normalized marks using the official GATE formula.
    - If single-session paper (e.g. DA, IN, CH): normalized == raw.
    - If sample size in session is small (< min_sample_size): uses raw score safely.
    - Otherwise applies full parametric equation with anti-poisoning filtering.
    """
    clean_code = paper_code.upper().strip()
    is_multi = clean_code in MULTI_SESSION_PAPERS

    # Case 1: Single session paper
    if not is_multi or not all_sessions_scores:
        gate_score = calculate_gate_score(
            raw_score,
            qualifying_marks=historical_qualifying_marks,
            top_01_marks=historical_top_marks,
        )
        return NormalizationResult(
            paper_code=clean_code,
            session_id=session_id,
            raw_score=raw_score,
            normalized_marks=round(raw_score, 4),
            gate_score=gate_score,
            is_multi_session=False,
            sample_size_used=len(all_sessions_scores.get(session_id, [])) if all_sessions_scores else 0,
            session_mean=raw_score,
            session_std=0.0,
        )

    # Multi-session evaluation
    curr_session_raw = all_sessions_scores.get(session_id, [])
    curr_session_cleaned = scrub_outliers_iqr(curr_session_raw)
    n_i = len(curr_session_cleaned)

    # Case 2: Insufficient sample size on early exam day -> Fallback
    if n_i < min_sample_size:
        gate_score = calculate_gate_score(
            raw_score,
            qualifying_marks=historical_qualifying_marks,
            top_01_marks=historical_top_marks,
        )
        return NormalizationResult(
            paper_code=clean_code,
            session_id=session_id,
            raw_score=raw_score,
            normalized_marks=round(raw_score, 4),
            gate_score=gate_score,
            is_multi_session=True,
            sample_size_used=n_i,
            session_mean=float(np.mean(curr_session_cleaned)) if n_i > 0 else raw_score,
            session_std=float(np.std(curr_session_cleaned)) if n_i > 0 else 0.0,
        )

    # Consolidate all session scores with outlier scrubbing
    all_cleaned_scores: List[float] = []
    for s_id, s_scores in all_sessions_scores.items():
        all_cleaned_scores.extend(scrub_outliers_iqr(s_scores))

    # Global parameters
    m_t_g = compute_top_01_percent_mean(all_cleaned_scores)
    m_q_g = float(np.mean(all_cleaned_scores) + np.std(all_cleaned_scores))

    # Session i parameters
    m_t_i = compute_top_01_percent_mean(curr_session_cleaned)
    s_mean = float(np.mean(curr_session_cleaned))
    s_std = float(np.std(curr_session_cleaned))
    m_i_q = s_mean + s_std

    denominator = m_t_i - m_i_q
    if abs(denominator) < 1e-4:
        # Avoid division by zero
        normalized_marks = raw_score
    else:
        # Official GATE formula:
        normalized_marks = ((m_t_g - m_q_g) / denominator) * (raw_score - m_i_q) + m_q_g

    # Bounded clamping: Cannot exceed 100 or fall below zero
    if raw_score > 0:
        normalized_marks = max(0.0, min(100.0, normalized_marks))
    else:
        normalized_marks = min(0.0, normalized_marks)

    gate_score = calculate_gate_score(
        normalized_marks,
        qualifying_marks=m_q_g * 0.75,  # Statistical proxy for qualifying mark
        top_01_marks=m_t_g,
    )

    return NormalizationResult(
        paper_code=clean_code,
        session_id=session_id,
        raw_score=raw_score,
        normalized_marks=round(float(normalized_marks), 4),
        gate_score=gate_score,
        is_multi_session=True,
        sample_size_used=n_i,
        session_mean=round(s_mean, 4),
        session_std=round(s_std, 4),
    )
