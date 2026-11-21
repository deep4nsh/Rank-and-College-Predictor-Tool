"""
Strictly Monotonic Score-to-Rank Predictor
Uses Piecewise Cubic Hermite Interpolating Polynomials (PCHIP) on log(AIR).
Guarantees d(AIR)/d(Score) < 0: A higher score NEVER receives a worse rank.
Incorporates live difficulty drift vector D = mu_live / mu_hist.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.interpolate import PchipInterpolator


# Historical (Score, AIR) benchmarks for major GATE papers
HISTORICAL_ANCHORS: Dict[str, List[Tuple[float, int]]] = {
    "CS": [
        (95.0, 1),
        (88.0, 10),
        (82.0, 50),
        (76.0, 120),
        (70.0, 280),
        (65.0, 600),
        (60.0, 1100),
        (55.0, 2000),
        (50.0, 3600),
        (45.0, 6200),
        (40.0, 10500),
        (35.0, 17000),
        (30.0, 26000),
        (25.0, 38000),
    ],
    "ME": [
        (92.0, 1),
        (85.0, 15),
        (78.0, 65),
        (72.0, 180),
        (66.0, 420),
        (60.0, 950),
        (54.0, 1900),
        (48.0, 3500),
        (42.0, 6500),
        (36.0, 11500),
        (30.0, 19000),
        (25.0, 30000),
    ],
    "CE": [
        (93.0, 1),
        (86.0, 12),
        (80.0, 55),
        (74.0, 160),
        (67.0, 400),
        (61.0, 900),
        (55.0, 1850),
        (49.0, 3400),
        (43.0, 6200),
        (37.0, 11000),
        (31.0, 18500),
        (25.0, 29000),
    ],
    "EE": [
        (91.0, 1),
        (84.0, 14),
        (77.0, 60),
        (70.0, 175),
        (64.0, 450),
        (58.0, 1050),
        (52.0, 2100),
        (46.0, 3900),
        (40.0, 7000),
        (34.0, 12000),
        (28.0, 20000),
    ],
    "EC": [
        (90.0, 1),
        (83.0, 12),
        (76.0, 58),
        (69.0, 165),
        (63.0, 430),
        (57.0, 1000),
        (51.0, 2050),
        (45.0, 3800),
        (39.0, 6900),
        (33.0, 11800),
        (27.0, 19500),
    ],
    "DA": [
        (94.0, 1),
        (86.0, 15),
        (79.0, 60),
        (73.0, 150),
        (67.0, 360),
        (61.0, 800),
        (55.0, 1600),
        (49.0, 3000),
        (43.0, 5500),
        (37.0, 9500),
        (31.0, 16000),
    ],
    "CH": [
        (91.0, 1),
        (83.0, 10),
        (76.0, 50),
        (69.0, 140),
        (62.0, 350),
        (55.0, 800),
        (48.0, 1600),
        (41.0, 3200),
        (34.0, 6000),
        (27.0, 11000),
    ],
    "IN": [
        (92.0, 1),
        (84.0, 8),
        (77.0, 40),
        (70.0, 110),
        (63.0, 280),
        (56.0, 650),
        (49.0, 1350),
        (42.0, 2700),
        (35.0, 5200),
        (28.0, 9500),
    ],
}


@dataclass
class RankPrediction:
    paper_code: str
    effective_score: float
    predicted_air: int
    air_range_min: int
    air_range_max: int
    drift_factor: float
    confidence_level: str  # "HIGH", "MODERATE", "ESTIMATED"


class MonotonicRankEngine:
    """
    Fits a PCHIP interpolator on (Score, ln(AIR)) for strict monotonicity.
    """

    def __init__(self, paper_code: str):
        self.paper_code = paper_code.upper().strip()
        anchors = HISTORICAL_ANCHORS.get(self.paper_code, HISTORICAL_ANCHORS["CS"])
        
        # Sort by score ascending for PCHIP
        sorted_anchors = sorted(anchors, key=lambda x: x[0])
        self.scores = np.array([x[0] for x in sorted_anchors], dtype=np.float64)
        # Using log of ranks prevents negative ranks and models the exponential distribution
        self.log_ranks = np.log(np.array([x[1] for x in sorted_anchors], dtype=np.float64))
        self.interpolator = PchipInterpolator(self.scores, self.log_ranks)

    def predict_rank(
        self,
        score: float,
        live_mean: Optional[float] = None,
        historical_mean: float = 30.0,
    ) -> RankPrediction:
        """
        Predicts AIR range with difficulty drift calibration.
        """
        # Calculate Difficulty Drift D
        if live_mean is not None and live_mean > 5.0 and historical_mean > 5.0:
            drift = float(live_mean / historical_mean)
            # Bound drift between 0.75 and 1.25 to prevent extreme distortion
            drift = max(0.75, min(1.25, drift))
        else:
            drift = 1.0

        # Calibrate score by shift difficulty
        # If paper is tougher (drift < 1.0), effective score is higher
        effective_score = score / drift
        clipped_score = max(float(self.scores[0]), min(float(self.scores[-1]), effective_score))

        # Evaluate PCHIP interpolator
        log_air = float(self.interpolator(clipped_score))
        predicted_air = max(1, int(round(np.exp(log_air))))

        # Compute error bands
        # At very top ranks (AIR < 100), uncertainty is smaller in absolute terms
        if predicted_air <= 50:
            margin = max(2, int(predicted_air * 0.20))
            confidence = "HIGH"
        elif predicted_air <= 500:
            margin = int(predicted_air * 0.15)
            confidence = "HIGH"
        elif predicted_air <= 2000:
            margin = int(predicted_air * 0.18)
            confidence = "MODERATE"
        else:
            margin = int(predicted_air * 0.22)
            confidence = "ESTIMATED"

        air_min = max(1, predicted_air - margin)
        air_max = predicted_air + margin

        return RankPrediction(
            paper_code=self.paper_code,
            effective_score=round(effective_score, 2),
            predicted_air=predicted_air,
            air_range_min=air_min,
            air_range_max=air_max,
            drift_factor=round(drift, 3),
            confidence_level=confidence,
        )
