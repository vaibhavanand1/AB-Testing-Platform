import math
from typing import Any, Dict, List, Optional
from scipy import stats

from app.config import settings


def calculate_two_sample_z_test(
    n_control: int,
    x_control: int,
    n_treatment: int,
    x_treatment: int,
    alpha: float = 0.05,
    min_sample_size: int = 100,
) -> Dict[str, Any]:
    # Guard against zero visitors
    if n_control == 0 or n_treatment == 0:
        return {
            "z_score": 0.0,
            "p_value": 1.0,
            "confidence_interval": [0.0, 0.0],
            "is_significant": False,
            "peeking_guard_active": True,
            "message": "Insufficient data: both variants must have at least 1 visitor.",
        }

    p_control = x_control / n_control
    p_treatment = x_treatment / n_treatment
    diff = p_treatment - p_control

    # Peeking guard: Require minimum sample size before declaring significance
    sample_guard_active = n_control < min_sample_size or n_treatment < min_sample_size

    # Handle zero conversions or identical extreme proportions
    total_conversions = x_control + x_treatment
    total_sample = n_control + n_treatment
    p_pool = total_conversions / total_sample

    if p_pool == 0.0 or p_pool == 1.0:
        return {
            "z_score": 0.0,
            "p_value": 1.0,
            "confidence_interval": [round(diff, 6), round(diff, 6)],
            "is_significant": False,
            "peeking_guard_active": sample_guard_active,
            "message": "Zero variance across variants; unable to test for significance.",
        }

    # Pooled standard error for the null hypothesis (p1 == p2)
    se_pool = math.sqrt(p_pool * (1.0 - p_pool) * (1.0 / n_control + 1.0 / n_treatment))

    if se_pool == 0.0:
        z_score = 0.0
        p_value = 1.0
    else:
        z_score = diff / se_pool
        # Two-tailed test
        p_value = float(2.0 * stats.norm.sf(abs(z_score)))

    # Unpooled standard error for confidence interval around the observed difference
    se_diff = math.sqrt(
        (p_control * (1.0 - p_control) / n_control)
        + (p_treatment * (1.0 - p_treatment) / n_treatment)
    )
    z_crit = float(stats.norm.ppf(1.0 - alpha / 2.0))
    margin_of_error = z_crit * se_diff
    ci_lower = diff - margin_of_error
    ci_upper = diff + margin_of_error

    # Significance requires both p < alpha AND passing the sample size peeking guard
    is_significant = (p_value < alpha) and not sample_guard_active

    if sample_guard_active:
        message = (
            f"Peeking guard active: sample size is under the threshold of {min_sample_size} "
            f"per variant (control: {n_control}, treatment: {n_treatment}). "
            f"Wait for adequate sample size to avoid false positives."
        )
    elif is_significant:
        message = (
            f"Statistically significant result detected at {(1 - alpha) * 100:.0f}% confidence level "
            f"(p = {p_value:.5f} < {alpha})."
        )
    else:
        message = f"No statistically significant difference detected (p = {p_value:.5f} >= {alpha})."

    return {
        "z_score": round(z_score, 4),
        "p_value": round(p_value, 5),
        "confidence_interval": [round(ci_lower, 5), round(ci_upper, 5)],
        "is_significant": is_significant,
        "peeking_guard_active": sample_guard_active,
        "message": message,
    }


def compute_experiment_results(
    variants: List[Dict[str, Any]],
    assignment_counts: Dict[str, int],
    conversion_counts: Dict[str, int],
) -> Dict[str, Any]:
    variant_stats = []
    for v in variants:
        v_name = v["name"]
        n = assignment_counts.get(v_name, 0)
        c = conversion_counts.get(v_name, 0)
        rate = c / n if n > 0 else 0.0
        variant_stats.append({
            "name": v_name,
            "weight": v.get("weight", 0),
            "sample_size": n,
            "conversions": c,
            "conversion_rate": round(rate, 4),
            "conversion_rate_percentage": round(rate * 100, 2),
        })

    # Designate control (first variant or variant explicitly named 'control')
    control_stat = next(
        (vs for vs in variant_stats if vs["name"].lower() == "control"),
        variant_stats[0] if variant_stats else None,
    )

    comparisons = []
    if control_stat and len(variant_stats) > 1:
        for treat_stat in variant_stats:
            if treat_stat["name"] == control_stat["name"]:
                continue

            test_result = calculate_two_sample_z_test(
                n_control=control_stat["sample_size"],
                x_control=control_stat["conversions"],
                n_treatment=treat_stat["sample_size"],
                x_treatment=treat_stat["conversions"],
                alpha=settings.significance_alpha,
                min_sample_size=settings.min_sample_size_per_variant,
            )

            ctrl_rate = control_stat["conversion_rate"]
            treat_rate = treat_stat["conversion_rate"]
            diff = treat_rate - ctrl_rate
            relative_lift = (diff / ctrl_rate * 100) if ctrl_rate > 0 else 0.0

            comparisons.append({
                "control_variant": control_stat["name"],
                "treatment_variant": treat_stat["name"],
                "absolute_diff": round(diff, 4),
                "relative_lift_percentage": round(relative_lift, 2),
                **test_result,
            })

    return {
        "variants": variant_stats,
        "comparisons": comparisons,
    }
