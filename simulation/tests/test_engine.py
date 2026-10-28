"""Unit tests for the deterministic simulation engine (no database).

Expected values are calculated by hand from the documented formulas so the
tests verify the real calculation rather than mocking it.
"""

from dataclasses import asdict

import pytest

from simulation import propagation as prop
from simulation.domain import Edge, Stage
from simulation.engine import SimulationConfigError, simulate

from .factories import STAGES, chain_edges, control, make_input


def states(result):
    return {s.key: s.state for s in result.stages}


class TestPropagation:
    def test_full_chain_propagates_when_probabilities_meet_threshold(self):
        result = simulate(make_input())
        assert states(result) == {
            "ide": "entry",
            "vcs": "compromised",
            "cicd": "compromised",
            "registry": "compromised",
            "production": "compromised",
        }
        assert result.compromised_count == 5

    def test_likelihood_multiplies_along_the_path(self):
        result = simulate(make_input())
        # 80, 80x0.8=64, 51.2, 40.96, 32.768 (rounded to 1 dp)
        assert [s.residual_likelihood for s in result.stages] == [80.0, 64.0, 51.2, 41.0, 32.8]

    def test_overall_risk_is_weighted_average(self):
        result = simulate(make_input())
        # (80x1 + 64x2 + 51.2x2 + 40.96x2 + 32.768x3) / 10 = 49.0624
        assert result.residual_risk == 49.1
        assert result.inherent_risk == 49.1
        assert result.peak_residual_risk == 80.0
        assert result.classification == "high"

    def test_edge_below_threshold_does_not_propagate(self):
        result = simulate(make_input(edges=chain_edges(probability=40)))
        assert states(result)["vcs"] == "exposed"
        assert states(result)["cicd"] == "unaffected"
        assert result.contained_count == 1
        # Exposed stage keeps the likelihood of its failed attempt: 80 x 0.4
        assert result.stage("vcs").residual_likelihood == 32.0

    def test_threshold_boundary_is_inclusive(self):
        at = simulate(make_input(edges=(Edge("ide", "vcs", 50),)))
        below = simulate(make_input(edges=(Edge("ide", "vcs", 49),)))
        assert states(at)["vcs"] == "compromised"
        assert states(below)["vcs"] == "exposed"

    def test_zero_probability_edge_never_propagates(self):
        result = simulate(make_input(edges=(Edge("ide", "vcs", 0),)))
        assert states(result)["vcs"] == "exposed"
        assert result.stage("vcs").residual_risk == 0

    def test_hundred_percent_edge_propagates_without_controls(self):
        result = simulate(make_input(edges=(Edge("ide", "vcs", 100),), threshold=100))
        assert states(result)["vcs"] == "compromised"

    def test_scenario_without_rules_only_affects_entry_stage(self):
        result = simulate(make_input(entry_stage="production", edges=()))
        assert states(result) == {
            "ide": "unaffected",
            "vcs": "unaffected",
            "cicd": "unaffected",
            "registry": "unaffected",
            "production": "entry",
        }
        assert result.evaluations == []

    def test_bypass_edge_skips_intermediate_stage(self):
        edges = (Edge("ide", "vcs", 10), Edge("ide", "cicd", 90))
        result = simulate(make_input(edges=edges))
        assert states(result)["vcs"] == "exposed"
        assert states(result)["cicd"] == "compromised"
        bypass = next(e for e in result.evaluations if e.target == "cicd")
        assert bypass.kind == prop.KIND_BYPASS

    def test_reverse_edge_is_classified(self):
        result = simulate(make_input(entry_stage="registry", edges=(Edge("registry", "cicd", 70),)))
        assert result.evaluations[0].kind == prop.KIND_REVERSE
        assert states(result)["cicd"] == "compromised"

    def test_most_likely_path_is_used(self):
        # via vcs: 80 x 1.0 x 0.6 = 48; direct: 80 x 0.55 = 44
        edges = (Edge("ide", "vcs", 100), Edge("vcs", "cicd", 60), Edge("ide", "cicd", 55))
        result = simulate(make_input(edges=edges))
        assert result.stage("cicd").residual_likelihood == 48.0

    def test_cycles_terminate_and_each_edge_is_evaluated_once(self):
        edges = (
            Edge("ide", "vcs", 80),
            Edge("vcs", "ide", 80),
            Edge("vcs", "cicd", 80),
            Edge("cicd", "vcs", 90),
        )
        result = simulate(make_input(edges=edges))
        assert len(result.evaluations) == 4
        back_edges = [e for e in result.evaluations if e.target in ("ide", "vcs") and e.source != "ide"]
        assert all(e.target_already_compromised for e in back_edges)
        assert states(result)["ide"] == "entry"
        assert result.stage("ide").residual_likelihood == 80.0

    def test_affected_and_unaffected_stages_identified(self):
        edges = (Edge("ide", "vcs", 90), Edge("vcs", "cicd", 20))
        result = simulate(make_input(edges=edges))
        assert states(result) == {
            "ide": "entry",
            "vcs": "compromised",
            "cicd": "exposed",
            "registry": "unaffected",
            "production": "unaffected",
        }
        assert result.stage("registry").residual_risk == 0


class TestControls:
    def test_preventive_control_blocks_propagation(self):
        result = simulate(make_input(controls=(control(effectiveness=50, stages=("vcs",)),)))
        assert states(result)["vcs"] == "blocked"
        assert states(result)["cicd"] == "unaffected"
        assert result.stage("vcs").inherent_state == "compromised"
        assert result.blocked_count == 1
        edge = result.evaluations[0]
        assert edge.outcome == prop.OUTCOME_BLOCKED
        assert edge.effective_probability == 40.0
        assert edge.controls == ("ctl",)

    def test_control_reduces_residual_but_not_inherent_risk(self):
        result = simulate(make_input(controls=(control(effectiveness=50, stages=("vcs",)),)))
        # residual: (80x1 + 32x2) / 10 = 14.4
        assert result.residual_risk == 14.4
        assert result.inherent_risk == 49.1
        assert result.classification == "low"

    def test_weak_control_reduces_likelihood_without_blocking(self):
        result = simulate(make_input(controls=(control(effectiveness=20, stages=("vcs",)),)))
        assert states(result)["vcs"] == "compromised"
        assert result.stage("vcs").residual_likelihood == 51.2  # 80 x 80 x 0.8 / 100
        assert result.residual_risk < result.inherent_risk

    def test_preventive_control_on_entry_stage_reduces_entry_likelihood(self):
        result = simulate(make_input(controls=(control(effectiveness=60, stages=("ide",)),)))
        assert result.stage("ide").residual_likelihood == 32.0
        assert result.stage("ide").inherent_likelihood == 80.0

    def test_mitigating_control_reduces_risk_but_not_propagation(self):
        detective = control("monitor", effectiveness=50, stages=("production",), category="detective")
        result = simulate(make_input(controls=(detective,)))
        assert states(result)["production"] == "compromised"
        assert result.stage("production").residual_risk == 16.4  # 32.768 x 0.5
        assert result.stage("production").mitigating_coverage == 50.0

    def test_multiple_controls_have_bounded_combined_effectiveness(self):
        controls = (
            control("a", 90, stages=("vcs",)),
            control("b", 90, stages=("vcs",)),
            control("c", 90, stages=("vcs",)),
        )
        result = simulate(make_input(controls=controls))
        assert result.stage("vcs").preventive_coverage == 99.9
        assert result.stage("vcs").preventive_coverage <= 100
        assert result.residual_risk >= 0

    def test_full_coverage_on_every_stage_leaves_no_risk(self):
        everything = control("all", 100, stages=[s.key for s in STAGES])
        result = simulate(make_input(controls=(everything,)))
        assert result.residual_risk == 0
        assert result.compromised_count == 1  # entry is still assumed compromised


class TestDeterminism:
    def test_identical_inputs_give_identical_results(self):
        inp = make_input(controls=(control(effectiveness=30, stages=("cicd",)),))
        assert asdict(simulate(inp)) == asdict(simulate(inp))

    def test_edge_order_does_not_change_result(self):
        edges = chain_edges() + (Edge("ide", "cicd", 70),)
        forward = simulate(make_input(edges=edges))
        backward = simulate(make_input(edges=tuple(reversed(edges))))
        assert asdict(forward) == asdict(backward)

    def test_explanation_mentions_entry_and_scores(self):
        result = simulate(make_input())
        text = " ".join(result.explanation)
        assert "IDE" in text and "49.1" in text
        assert result.limitations


class TestValidation:
    @pytest.mark.parametrize(
        ("overrides", "message"),
        [
            ({"entry_stage": "nowhere"}, "Unknown entry stage"),
            ({"likelihood": 101}, "Likelihood"),
            ({"likelihood": -1}, "Likelihood"),
            ({"severity": 0}, "Severity"),
            ({"impact": 6}, "Impact"),
            ({"threshold": 0}, "threshold"),
            ({"threshold": 150}, "threshold"),
            ({"edges": (Edge("ide", "ide", 50),)}, "itself"),
            ({"edges": (Edge("ide", "vcs", 50), Edge("ide", "vcs", 60))}, "Duplicate"),
            ({"edges": (Edge("ide", "mars", 50),)}, "unknown stage"),
            ({"edges": (Edge("ide", "vcs", 120),)}, "Probability"),
            ({"stages": ()}, "at least one stage"),
            ({"controls": (control("x"), control("x"))}, "only be enabled once"),
            ({"controls": (control("x", stages=("moon",)),)}, "unknown stage"),
            ({"controls": (control("x", effectiveness=101),)}, "Effectiveness"),
        ],
    )
    def test_invalid_configuration_is_rejected(self, overrides, message):
        with pytest.raises(SimulationConfigError, match=message):
            simulate(make_input(**overrides))

    def test_duplicate_stage_keys_rejected(self):
        stages = STAGES + (Stage("ide", "Copy", 9),)
        with pytest.raises(SimulationConfigError, match="unique"):
            simulate(make_input(stages=stages))

    def test_invalid_stage_weight_rejected(self):
        stages = (Stage("ide", "IDE", 1, 0),)
        with pytest.raises(SimulationConfigError, match="weight"):
            simulate(make_input(stages=stages, edges=()))

    def test_zero_likelihood_gives_zero_risk(self):
        result = simulate(make_input(likelihood=0))
        assert result.residual_risk == 0
        assert result.inherent_risk == 0
