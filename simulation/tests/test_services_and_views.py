import csv
import io
from unittest import mock

import pytest
from django.urls import reverse

from audit.models import AuditAction, AuditEvent
from simulation import services
from simulation.engine import SimulationConfigError, simulate
from simulation.exports import safe_cell
from simulation.models import PropagationEvent, RunStatus, SimulationRun, SimulationStageResult
from threats.models import PropagationRule, SecurityControl, ThreatScenario

pytestmark = pytest.mark.django_db

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def run_for(user, slug="compromised-developer-account", controls=(), **overrides):
    scenario = ThreatScenario.objects.get(slug=slug)
    params = {
        "likelihood": scenario.likelihood,
        "severity": scenario.severity,
        "impact": scenario.impact,
        "threshold": scenario.propagation_threshold,
    }
    params.update(overrides)
    return services.run_simulation(user, scenario, controls=SecurityControl.objects.filter(slug__in=controls), **params)


class TestRunPersistence:
    def test_completed_run_is_saved_with_children(self, seeded, analyst):
        run = run_for(analyst)
        assert run.status == RunStatus.COMPLETED
        assert run.completed_at is not None
        assert SimulationStageResult.objects.filter(run=run).count() == 5
        assert PropagationEvent.objects.filter(run=run).count() == 5
        assert run.inherent_risk == 26.6  # verified against the seeded scenario by hand
        assert run.residual_risk == run.inherent_risk  # no controls enabled
        assert run.result["recommendations"]
        assert AuditEvent.objects.filter(action=AuditAction.SIMULATION_RUN, actor=analyst).exists()

    def test_controls_reduce_stored_residual_risk(self, seeded, analyst):
        run = run_for(analyst, controls=["mfa", "protected-branches"])
        assert run.residual_risk < run.inherent_risk
        assert run.enabled_controls == ["mfa", "protected-branches"]
        assert run.result["control_contributions"]

    def test_snapshot_reproduces_the_stored_result(self, seeded, analyst):
        run = run_for(analyst, controls=["mfa"])
        rebuilt = simulate(services.input_from_snapshot(run.input_snapshot))
        assert rebuilt.residual_risk == run.residual_risk
        assert rebuilt.inherent_risk == run.inherent_risk

    def test_snapshot_records_the_assumptions_of_enabled_controls(self, seeded, analyst):
        run = run_for(analyst, controls=["mfa"])
        assert run.input_snapshot["snapshot_version"] == 2
        recorded = run.input_snapshot["control_assumptions"]
        assert list(recorded) == ["mfa"]
        assert recorded["mfa"]["effectiveness"] == 60
        assert "phishing-resistant" in recorded["mfa"]["basis"]
        assert "session-token theft" in recorded["mfa"]["limitations"]
        # Later catalog edits do not rewrite what the run assumed.
        SecurityControl.objects.filter(slug="mfa").update(limitations="changed")
        run.refresh_from_db()
        assert "session-token theft" in run.input_snapshot["control_assumptions"]["mfa"]["limitations"]

    def test_every_seeded_control_states_its_basis_and_limitations(self, seeded, analyst_client):
        for control in SecurityControl.objects.all():
            assert control.effectiveness_basis and control.limitations, control.slug
        page = analyst_client.get(reverse("threats:control_detail", args=["mfa"])).content.decode()
        assert "Assumptions and limitations" in page and "session-token theft" in page

    def test_historical_report_is_stable_after_scenario_edit(self, seeded, analyst, client):
        run = run_for(analyst)
        scenario = run.scenario
        scenario.likelihood = 5
        scenario.version += 1
        scenario.save()
        PropagationRule.objects.filter(scenario=scenario).update(probability=1)

        run.refresh_from_db()
        assert run.residual_risk == 26.6
        assert run.input_snapshot["scenario"]["version"] == 1
        assert run.input_snapshot["input"]["likelihood"] == 70
        client.force_login(analyst)
        page = client.get(reverse("simulation:detail", args=[run.id]))
        assert b"has been edited since this run" in page.content
        assert b"26.6" in page.content

    def test_run_survives_scenario_deletion(self, seeded, analyst):
        scenario = ThreatScenario.objects.get(slug="compromised-developer-account")
        from threats.services import clone_scenario

        clone = clone_scenario(scenario, analyst)
        run = run_for(analyst, slug=clone.slug)
        clone.delete()
        run.refresh_from_db()
        assert run.scenario is None
        assert run.scenario_name == clone.name
        assert run.stage_results.count() == 5

    def test_invalid_configuration_creates_no_run(self, seeded, analyst):
        with pytest.raises(SimulationConfigError):
            run_for(analyst, likelihood=150)
        assert SimulationRun.objects.count() == 0

    def test_failure_marks_run_failed_without_partial_results(self, seeded, analyst):
        with mock.patch("simulation.services.recommend", side_effect=RuntimeError("boom")):
            run = run_for(analyst)
        assert run.status == RunStatus.FAILED
        assert "boom" not in run.error_message  # internal details are not exposed
        assert run.stage_results.count() == 0
        assert run.events.count() == 0
        assert run.residual_risk is None
        assert AuditEvent.objects.filter(action=AuditAction.SIMULATION_FAILED).exists()


class TestConfigureView:
    def test_configure_prefills_scenario_values(self, seeded, analyst_client):
        response = analyst_client.get(reverse("simulation:configure"), {"scenario": "compromised-cicd-pipeline"})
        assert response.status_code == 200
        assert response.context["form"].initial["likelihood"] == 55

    def test_post_runs_simulation_and_redirects(self, seeded, analyst_client):
        mfa = SecurityControl.objects.get(slug="mfa")
        response = analyst_client.post(
            reverse("simulation:configure"),
            {
                "scenario": "compromised-developer-account",
                "likelihood": 70,
                "severity": 4,
                "impact": 4,
                "threshold": 50,
                "controls": [mfa.pk],
            },
        )
        run = SimulationRun.objects.get()
        assert response.status_code == 302
        assert response.url == reverse("simulation:detail", args=[run.id])
        assert run.enabled_controls == ["mfa"]

    @pytest.mark.parametrize(
        "field,value", [("likelihood", 101), ("likelihood", -5), ("severity", 0), ("impact", 9), ("threshold", 0)]
    )
    def test_out_of_range_values_are_rejected(self, seeded, analyst_client, field, value):
        data = {
            "scenario": "compromised-developer-account",
            "likelihood": 70,
            "severity": 4,
            "impact": 4,
            "threshold": 50,
        }
        data[field] = value
        response = analyst_client.post(reverse("simulation:configure"), data)
        assert response.status_code == 200
        assert field in response.context["form"].errors
        assert SimulationRun.objects.count() == 0

    def test_cannot_run_another_users_private_scenario(self, seeded, analyst_client, other_analyst):
        from threats.services import clone_scenario

        private = clone_scenario(ThreatScenario.objects.first(), other_analyst)
        response = analyst_client.post(
            reverse("simulation:configure"),
            {"scenario": private.slug, "likelihood": 50, "severity": 3, "impact": 3, "threshold": 50},
        )
        assert response.status_code == 200
        assert "scenario" in response.context["form"].errors
        assert SimulationRun.objects.count() == 0
        # The rejection is shown to the user, not silently swallowed.
        assert b"The simulation was not run." in response.content
        assert b"not available to you" in response.content

    def test_viewer_role_denial_does_not_reveal_whether_a_private_scenario_exists(
        self, seeded, viewer_client, other_analyst
    ):
        from threats.services import clone_scenario

        private = clone_scenario(ThreatScenario.objects.first(), other_analyst)
        for action in ("edit", "delete"):
            real = viewer_client.get(reverse(f"threats:{action}", args=[private.slug]))
            fake = viewer_client.get(reverse(f"threats:{action}", args=["no-such-scenario"]))
            assert real.status_code == fake.status_code == 403

    def test_viewer_cannot_run_simulations(self, seeded, viewer_client):
        assert viewer_client.get(reverse("simulation:configure")).status_code == 403
        response = viewer_client.post(
            reverse("simulation:configure"),
            {
                "scenario": "compromised-developer-account",
                "likelihood": 50,
                "severity": 3,
                "impact": 3,
                "threshold": 50,
            },
        )
        assert response.status_code == 403
        assert SimulationRun.objects.count() == 0

    def test_rerun_prefills_from_previous_run(self, seeded, analyst, analyst_client):
        run = run_for(analyst, controls=["mfa"], likelihood=40)
        response = analyst_client.get(reverse("simulation:configure"), {"rerun": str(run.id)})
        assert response.context["form"].initial["likelihood"] == 40
        assert [c.slug for c in response.context["form"].initial["controls"]] == ["mfa"]


class TestReportAccess:
    def test_owner_sees_report_with_charts(self, seeded, analyst, analyst_client):
        run = run_for(analyst)
        response = analyst_client.get(reverse("simulation:detail", args=[run.id]))
        assert response.status_code == 200
        assert b"Supply chain propagation" in response.content
        for kind in ("overall", "stages", "outcomes"):
            chart = analyst_client.get(reverse("simulation:chart", args=[run.id, kind]))
            assert chart.status_code == 200
            assert chart["Content-Type"] == "image/png"
            assert chart.content.startswith(PNG_MAGIC)

    def test_chart_follows_the_requested_theme_palette(self, seeded, analyst, analyst_client):
        run = run_for(analyst)
        url = reverse("simulation:chart", args=[run.id, "overall"])
        dark = "1E1A17,EDE6DA,9A8F80,2E2822,3D352D,4CC38A,E8B04B,F0654F,FF8A7A"
        light = analyst_client.get(url).content
        themed = analyst_client.get(url, {"palette": dark})
        assert themed.status_code == 200
        assert themed.content.startswith(PNG_MAGIC)
        assert themed.content != light
        # A malformed palette falls back to the default (light) chart instead of failing.
        for bad in ("red", "1E1A17", "ZZZZZZ," * 8 + "ZZZZZZ", "url(x)," * 9):
            assert analyst_client.get(url, {"palette": bad}).content == light

    def test_unknown_chart_kind_is_404(self, seeded, analyst, analyst_client):
        run = run_for(analyst)
        assert analyst_client.get(reverse("simulation:chart", args=[run.id, "secrets"])).status_code == 404

    def test_other_user_cannot_open_private_report_chart_or_csv(self, seeded, analyst, client, other_analyst):
        run = run_for(analyst)
        client.force_login(other_analyst)
        for url in (
            reverse("simulation:detail", args=[run.id]),
            reverse("simulation:chart", args=[run.id, "overall"]),
            reverse("simulation:export_run", args=[run.id]),
            reverse("simulation:compare") + f"?a={run.id}&b={run.id}",
        ):
            assert client.get(url).status_code == 404, url

    def test_shared_report_visible_read_only_to_viewer(self, seeded, analyst, analyst_client, client, viewer):
        run = run_for(analyst)
        analyst_client.post(reverse("simulation:share", args=[run.id]))
        run.refresh_from_db()
        assert run.is_shared
        client.force_login(viewer)
        assert client.get(reverse("simulation:detail", args=[run.id])).status_code == 200
        # The viewer cannot change sharing on someone else's report.
        assert client.post(reverse("simulation:share", args=[run.id])).status_code == 403

    def test_anonymous_users_are_redirected_to_login(self, seeded, analyst, client):
        run = run_for(analyst)
        for url in (
            reverse("simulation:detail", args=[run.id]),
            reverse("simulation:chart", args=[run.id, "overall"]),
            reverse("reports:list"),
        ):
            response = client.get(url)
            assert response.status_code == 302
            assert reverse("accounts:login") in response.url

    def test_history_lists_only_own_runs_by_default(self, seeded, analyst, other_analyst, analyst_client):
        mine = run_for(analyst)
        run_for(other_analyst)
        response = analyst_client.get(reverse("reports:list"))
        assert list(response.context["page_obj"]) == [mine]

    def test_csv_export_contains_results_and_is_audited(self, seeded, analyst, analyst_client):
        run = run_for(analyst)
        response = analyst_client.get(reverse("simulation:export_run", args=[run.id]))
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        rows = list(csv.reader(io.StringIO(response.content.decode())))
        assert rows[1] == ["Run ID", str(run.id)]
        assert any(row[:1] == ["IDE / Developer Environment"] for row in rows)
        assert AuditEvent.objects.filter(action=AuditAction.REPORT_EXPORT).exists()

    def test_history_csv_contains_only_own_runs(self, seeded, analyst, other_analyst, analyst_client):
        run_for(analyst)
        other = run_for(other_analyst)
        response = analyst_client.get(reverse("reports:export_history"))
        body = response.content.decode()
        assert str(other.id) not in body
        assert body.count("\n") == 2  # header + one run

    def test_csv_cells_are_protected_against_formula_injection(self):
        assert safe_cell("=HYPERLINK()") == "'=HYPERLINK()"
        assert safe_cell("+1") == "'+1"
        assert safe_cell("normal") == "normal"
        assert safe_cell(5) == 5


class TestComparison:
    def test_before_after_comparison(self, seeded, analyst, analyst_client):
        before = run_for(analyst)
        after = run_for(analyst, controls=["mfa", "protected-branches"])
        response = analyst_client.get(reverse("simulation:compare"), {"a": before.id, "b": after.id})
        assert response.status_code == 200
        comparison = response.context["comparison"]
        assert comparison["delta"] == round(after.residual_risk - before.residual_risk, 1)
        assert comparison["delta"] < 0
        assert comparison["controls_added"] == ["mfa", "protected-branches"]
        assert any(row["state_changed"] for row in comparison["rows"])
        chart = analyst_client.get(reverse("simulation:compare_chart"), {"a": before.id, "b": after.id})
        assert chart.content.startswith(PNG_MAGIC)

    def test_compare_select_page_lists_runs(self, seeded, analyst, analyst_client):
        run_for(analyst)
        response = analyst_client.get(reverse("simulation:compare"))
        assert response.status_code == 200
        assert len(response.context["runs"]) == 1
