import pytest
from app.hashing import compute_variant
from app.stats import calculate_two_sample_z_test, compute_experiment_results


def test_consistent_hashing_deterministic():
    variants = [
        {"name": "control", "weight": 50},
        {"name": "treatment", "weight": 50},
    ]
    # Same user and experiment should yield identical assignment repeatedly
    res1 = compute_variant(1, "user_xyz_123", variants)
    res2 = compute_variant(1, "user_xyz_123", variants)
    assert res1 == res2


def test_consistent_hashing_distribution_50_50():
    variants = [
        {"name": "control", "weight": 50},
        {"name": "treatment", "weight": 50},
    ]
    counts = {"control": 0, "treatment": 0}
    n = 10000
    for i in range(n):
        assigned = compute_variant(1, f"user_{i}", variants)
        counts[assigned] += 1

    # With 10,000 samples and 50/50 split, should be within 48% - 52%
    control_pct = counts["control"] / n
    treatment_pct = counts["treatment"] / n
    assert 0.48 <= control_pct <= 0.52
    assert 0.48 <= treatment_pct <= 0.52


def test_consistent_hashing_distribution_70_30():
    variants = [
        {"name": "control", "weight": 70},
        {"name": "treatment", "weight": 30},
    ]
    counts = {"control": 0, "treatment": 0}
    n = 10000
    for i in range(n):
        assigned = compute_variant(1, f"user_{i}", variants)
        counts[assigned] += 1

    control_pct = counts["control"] / n
    treatment_pct = counts["treatment"] / n
    assert 0.68 <= control_pct <= 0.72
    assert 0.28 <= treatment_pct <= 0.32


def test_peeking_guard_prevents_early_significance():
    # Even if p-value is tiny, sample size under 100 must flag peeking guard
    res = calculate_two_sample_z_test(
        n_control=20,
        x_control=1,   # 5%
        n_treatment=20,
        x_treatment=10, # 50%
        alpha=0.05,
        min_sample_size=100,
    )
    assert res["peeking_guard_active"] is True
    assert res["is_significant"] is False


def test_z_test_significant_difference():
    # Control: 1000 visitors, 100 conversions (10%)
    # Treatment: 1000 visitors, 150 conversions (15%)
    # This should be statistically significant at alpha = 0.05
    res = calculate_two_sample_z_test(
        n_control=1000,
        x_control=100,
        n_treatment=1000,
        x_treatment=150,
        alpha=0.05,
        min_sample_size=100,
    )
    assert res["peeking_guard_active"] is False
    assert res["is_significant"] is True
    assert res["p_value"] < 0.01
    assert res["confidence_interval"][0] > 0  # CI is entirely above 0


def test_z_test_zero_conversions_edge_case():
    res = calculate_two_sample_z_test(
        n_control=200,
        x_control=0,
        n_treatment=200,
        x_treatment=0,
        alpha=0.05,
        min_sample_size=100,
    )
    assert res["z_score"] == 0.0
    assert res["p_value"] == 1.0
    assert res["is_significant"] is False
