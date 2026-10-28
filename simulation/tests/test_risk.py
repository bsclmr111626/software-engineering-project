import math

import pytest

from simulation import risk


class TestRawAndResidualRisk:
    def test_raw_risk_uses_documented_formula(self):
        # 80 x (4/5) x (3/5) = 38.4
        assert risk.raw_risk(80, 4, 3) == pytest.approx(38.4)

    def test_raw_risk_maximum_inputs_give_100(self):
        assert risk.raw_risk(100, 5, 5) == pytest.approx(100.0)

    def test_raw_risk_zero_likelihood_gives_zero(self):
        assert risk.raw_risk(0, 5, 5) == 0

    def test_raw_risk_minimum_severity_and_impact(self):
        # 100 x 1/5 x 1/5 = 4
        assert risk.raw_risk(100, 1, 1) == pytest.approx(4.0)

    def test_residual_risk_applies_coverage(self):
        assert risk.residual_risk(60.0, 25.0) == pytest.approx(45.0)

    def test_full_coverage_removes_all_risk(self):
        assert risk.residual_risk(60.0, 100.0) == 0

    @pytest.mark.parametrize("likelihood", [-1, 100.1, math.nan, math.inf, "50", None, True])
    def test_invalid_likelihood_rejected(self, likelihood):
        with pytest.raises(risk.RiskInputError):
            risk.raw_risk(likelihood, 3, 3)

    @pytest.mark.parametrize("level", [0, 6, 2.5, "3", True])
    def test_invalid_severity_rejected(self, level):
        with pytest.raises(risk.RiskInputError):
            risk.raw_risk(50, level, 3)

    @pytest.mark.parametrize("level", [0, 6])
    def test_invalid_impact_rejected(self, level):
        with pytest.raises(risk.RiskInputError):
            risk.raw_risk(50, 3, level)

    def test_invalid_coverage_rejected(self):
        with pytest.raises(risk.RiskInputError):
            risk.residual_risk(50, 101)


class TestCombinedEffectiveness:
    def test_no_controls_means_zero_coverage(self):
        assert risk.combined_effectiveness([]) == 0

    def test_single_control_is_unchanged(self):
        assert risk.combined_effectiveness([60]) == pytest.approx(60.0)

    def test_two_controls_combine_multiplicatively(self):
        # 1 - (0.5 x 0.5) = 75%
        assert risk.combined_effectiveness([50, 50]) == pytest.approx(75.0)

    def test_combined_coverage_never_exceeds_100(self):
        assert risk.combined_effectiveness([90, 90, 90, 90]) < 100
        assert risk.combined_effectiveness([100, 100]) == pytest.approx(100.0)

    def test_invalid_effectiveness_rejected(self):
        with pytest.raises(risk.RiskInputError):
            risk.combined_effectiveness([120])


class TestRoundingAndClassification:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [(12.25, 12.3), (12.35, 12.4), (12.24, 12.2), (0.05, 0.1), (99.95, 100.0), (-3, 0.0), (140, 100.0)],
    )
    def test_round_half_up_and_clamp(self, value, expected):
        assert risk.round_score(value) == expected

    @pytest.mark.parametrize(
        ("score", "label"),
        [
            (0, "low"),
            (14.9, "low"),
            (15, "moderate"),
            (29.9, "moderate"),
            (30, "high"),
            (49.9, "high"),
            (50, "critical"),
            (100, "critical"),
        ],
    )
    def test_classification_band_boundaries(self, score, label):
        assert risk.classify(score) == label

    def test_weighted_overall_average(self):
        # (10x1 + 40x3) / 4 = 32.5
        assert risk.weighted_overall([(10, 1), (40, 3)]) == pytest.approx(32.5)

    def test_weighted_overall_empty_is_zero(self):
        assert risk.weighted_overall([]) == 0

    def test_threshold_comparison_ignores_float_noise(self):
        assert risk.meets_threshold(49.99999999999, 50)
        assert not risk.meets_threshold(49.9, 50)
