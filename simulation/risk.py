"""Risk formulas used by the CodeGuard simulation engine.

All functions are pure: the same input always produces the same output.
Percentages use a 0-100 scale; severity and impact use a 1-5 ordinal scale.

    Raw risk       = likelihood x (severity / 5) x (impact / 5)
    Residual risk  = raw risk x (1 - mitigating coverage / 100)
    Combined effectiveness of independent controls = 1 - product(1 - e_i)
    Overall risk   = criticality-weighted average of stage risks
"""

import math
from decimal import ROUND_HALF_UP, Decimal

LEVEL_MIN = 1
LEVEL_MAX = 5

# Classification bands for 0-100 scores: (inclusive lower bound, label).
RISK_BANDS = (
    (50.0, "critical"),
    (30.0, "high"),
    (15.0, "moderate"),
    (0.0, "low"),
)

# Comparisons against thresholds are made on values rounded to this many
# decimal places so floating point noise (49.9999999) cannot flip a decision.
DECISION_PRECISION = 6


class RiskInputError(ValueError):
    """Raised when a risk parameter is outside its documented range."""


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def validate_percentage(value, name):
    if not _is_number(value) or not 0 <= value <= 100:
        raise RiskInputError(f"{name} must be a number between 0 and 100 (got {value!r}).")
    return float(value)


def validate_level(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or not LEVEL_MIN <= value <= LEVEL_MAX:
        raise RiskInputError(f"{name} must be a whole number between {LEVEL_MIN} and {LEVEL_MAX} (got {value!r}).")
    return value


def round_score(value):
    """Clamp to 0-100 and round half-up to one decimal place."""
    clamped = min(100.0, max(0.0, float(value)))
    return float(Decimal(str(clamped)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def combined_effectiveness(effectivenesses):
    """Combine independent control effectiveness values (each 0-100).

    Assumes controls act independently, so coverage can approach but never
    exceed 100%: 1 - product(1 - e_i).
    """
    remaining = 1.0
    for value in effectivenesses:
        remaining *= 1 - validate_percentage(value, "Control effectiveness") / 100
    return 100.0 * (1 - remaining)


def raw_risk(likelihood, severity, impact):
    """Inherent risk on a 0-100 scale (unrounded)."""
    validate_percentage(likelihood, "Likelihood")
    validate_level(severity, "Severity")
    validate_level(impact, "Impact")
    return likelihood * (severity / LEVEL_MAX) * (impact / LEVEL_MAX)


def residual_risk(raw, coverage):
    """Reduce a raw risk value by a control coverage percentage (unrounded)."""
    validate_percentage(coverage, "Control coverage")
    return raw * (1 - coverage / 100)


def weighted_overall(scores_and_weights):
    """Criticality-weighted average of (score, weight) pairs, 0 when empty."""
    pairs = list(scores_and_weights)
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:
        return 0.0
    return sum(score * weight for score, weight in pairs) / total_weight


def classify(score):
    for lower_bound, label in RISK_BANDS:
        if score >= lower_bound:
            return label
    return "low"


def meets_threshold(value, threshold):
    return round(value, DECISION_PRECISION) >= round(threshold, DECISION_PRECISION)
