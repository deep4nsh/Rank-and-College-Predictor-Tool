from backend.app.core.rank_spline import MonotonicRankEngine


def test_strict_rank_monotonicity():
    engine = MonotonicRankEngine("CS")

    # Higher score must ALWAYS yield a better (smaller) AIR
    scores = [92.0, 85.0, 78.0, 70.0, 62.0, 55.0, 48.0, 40.0, 32.0]
    ranks = [engine.predict_rank(s).predicted_air for s in scores]

    for i in range(len(ranks) - 1):
        assert ranks[i] < ranks[i + 1], f"Monotonicity broken: score {scores[i]} gave rank {ranks[i]}, score {scores[i+1]} gave rank {ranks[i+1]}"


def test_air_bounds_positive():
    engine = MonotonicRankEngine("ME")
    res_top = engine.predict_rank(95.0)
    assert res_top.predicted_air >= 1
    assert res_top.air_range_min >= 1
    assert res_top.confidence_level == "HIGH"

    res_low = engine.predict_rank(25.0)
    assert res_low.predicted_air > 10000
    assert res_low.air_range_max > res_low.air_range_min


def test_difficulty_drift_adjustment():
    engine = MonotonicRankEngine("CS")

    # Baseline prediction with normal drift (live_mean == historical_mean)
    normal = engine.predict_rank(65.0, live_mean=30.0, historical_mean=30.0)

    # When live shift is tougher (live_mean=25.0 vs historical 30.0), D < 1.0
    tough_shift = engine.predict_rank(65.0, live_mean=24.0, historical_mean=30.0)

    # 65 marks in a tough shift represents a better effective score and better AIR
    assert tough_shift.effective_score > normal.effective_score
    assert tough_shift.predicted_air < normal.predicted_air
