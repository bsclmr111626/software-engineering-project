from simulation.engine import simulate
from simulation.recommendations import control_contributions, recommend
from simulation.serialization import input_to_dict, result_to_dict

from .factories import control, make_input


def test_recommendation_reports_exact_modeled_reduction():
    inp = make_input()
    result = simulate(inp)
    candidate = control("branch", effectiveness=50, stages=("vcs",))
    recs = recommend(inp, result, [candidate], applicable_keys={"branch"})
    assert len(recs) == 1
    rec = recs[0]
    # 49.1 -> 14.4 (see engine tests)
    assert rec.current_risk == 49.1
    assert rec.projected_risk == 14.4
    assert rec.risk_reduction == 34.7
    assert rec.scenario_applicable
    assert "Version Control" in rec.protected_stages
    assert rec.stages_no_longer_compromised == ["Version Control", "CI/CD", "Registry", "Production"]
    assert rec.edges_addressed == ["IDE → Version Control: 80.0% → 40.0%"]


def test_enabled_and_useless_controls_are_not_recommended():
    enabled = control("on", effectiveness=50, stages=("vcs",))
    inp = make_input(controls=(enabled,))
    result = simulate(inp)
    unreachable = control("prod-only", effectiveness=50, stages=("production",))
    assert recommend(inp, result, [enabled, unreachable]) == []


def test_recommendations_are_ranked_by_reduction():
    inp = make_input()
    result = simulate(inp)
    small = control("small", effectiveness=10, stages=("production",), category="detective")
    big = control("big", effectiveness=60, stages=("ide",))
    recs = recommend(inp, result, [small, big])
    assert [r.control for r in recs] == ["big", "small"]
    assert recs[0].risk_reduction > recs[1].risk_reduction


def test_recommendation_limit():
    inp = make_input()
    result = simulate(inp)
    catalog = [control(f"c{i}", effectiveness=10 + i, stages=("production",)) for i in range(8)]
    assert len(recommend(inp, result, catalog, limit=3)) == 3


def test_control_contribution_is_leave_one_out():
    enabled = control("branch", effectiveness=50, stages=("vcs",))
    inp = make_input(controls=(enabled,))
    result = simulate(inp)
    [contribution] = control_contributions(inp, result)
    assert contribution.risk_without == 49.1
    assert contribution.risk_with == 14.4
    assert contribution.contribution == 34.7


def test_serialization_is_json_safe():
    import json

    inp = make_input(controls=(control(stages=("vcs", "cicd")),))
    result = simulate(inp)
    data = result_to_dict(result, recommend(inp, result, [control("x", stages=("ide",))]))
    json.dumps(data)
    json.dumps(input_to_dict(inp))
    assert input_to_dict(inp)["controls"][0]["stages"] == ["cicd", "vcs"]
    assert data["recommendations"][0]["control"] == "x"
