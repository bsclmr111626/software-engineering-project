"""End-to-end workflow tests through the real URL routes, plus project checks."""

import io

import pytest
from django.core.management import call_command
from django.urls import reverse

from simulation.models import RunStatus, SimulationRun
from threats.models import SecurityControl

pytestmark = pytest.mark.django_db


def test_migrations_are_consistent_with_models():
    out = io.StringIO()
    call_command("makemigrations", "--check", "--dry-run", stdout=out)
    assert "No changes detected" in out.getvalue()


def test_system_checks_pass():
    call_command("check")


def test_complete_analyst_journey(seeded, client):
    # 1. Register (role is assigned by the server)
    response = client.post(
        reverse("accounts:register"),
        {
            "username": "student",
            "email": "s@example.com",
            "password1": "Lean-and-secure-42",
            "password2": "Lean-and-secure-42",
        },
    )
    assert response.status_code == 302

    # 2. Browse the library and a scenario
    assert client.get(reverse("threats:list")).status_code == 200
    assert client.get(reverse("threats:detail", args=["compromised-developer-account"])).status_code == 200

    # 3. Run a baseline simulation with no controls
    base = {"scenario": "compromised-developer-account", "likelihood": 70, "severity": 4, "impact": 4, "threshold": 50}
    client.post(reverse("simulation:configure"), base)
    baseline = SimulationRun.objects.get()
    assert baseline.status == RunStatus.COMPLETED
    assert baseline.compromised_count == 5

    # 4. Follow the top recommendation and rerun
    top = baseline.result["recommendations"][0]["control"]
    control = SecurityControl.objects.get(slug=top)
    client.post(reverse("simulation:configure"), {**base, "controls": [control.pk]})
    improved = SimulationRun.objects.exclude(pk=baseline.pk).get()
    assert improved.residual_risk < baseline.residual_risk
    assert improved.compromised_count < baseline.compromised_count

    # 5. The report links to the comparison, which shows the improvement
    detail = client.get(reverse("simulation:detail", args=[improved.id]))
    assert detail.context["previous"] == baseline
    compare = client.get(reverse("simulation:compare"), {"a": baseline.id, "b": improved.id})
    assert compare.context["comparison"]["delta"] < 0

    # 6. History, export and dashboard all reflect the two runs
    assert client.get(reverse("reports:list")).context["page_obj"].paginator.count == 2
    assert client.get(reverse("simulation:export_run", args=[improved.id])).status_code == 200
    assert client.get(reverse("core:dashboard")).context["metrics"]["run_total"] == 2

    # 7. Audit trail records the journey
    actions = {event.action for event in client.get(reverse("audit:log")).context["page_obj"]}
    assert {"register", "simulation_run", "report_export"} <= actions

    # 8. Sign out
    client.post(reverse("accounts:logout"))
    assert client.get(reverse("core:dashboard")).status_code == 302


@pytest.mark.parametrize(
    "url_name",
    ["core:dashboard", "threats:list", "threats:controls", "threats:create", "reports:list",
     "simulation:configure", "simulation:compare", "audit:log", "core:help", "accounts:password_change",
     "simulation:hub", "simulation:results", "core:supply_chain", "core:risk", "core:notifications",
     "remediation:plan", "settings:profile", "settings:account", "settings:appearance", "settings:typography",
     "settings:display", "settings:accessibility", "settings:notifications", "settings:privacy",
     "settings:security", "settings:sessions"],
)  # fmt: skip
def test_every_main_page_renders_for_analyst(seeded, analyst_client, url_name):
    assert analyst_client.get(reverse(url_name)).status_code == 200


def test_every_seeded_scenario_simulates_successfully(seeded, analyst_client):
    from threats.models import ThreatScenario

    for scenario in ThreatScenario.objects.all():
        response = analyst_client.post(
            reverse("simulation:configure"),
            {"scenario": scenario.slug, "likelihood": scenario.likelihood, "severity": scenario.severity,
             "impact": scenario.impact, "threshold": scenario.propagation_threshold},
        )  # fmt: skip
        assert response.status_code == 302, scenario.slug
    assert SimulationRun.objects.filter(status=RunStatus.COMPLETED).count() == 6
    for run in SimulationRun.objects.all():
        assert analyst_client.get(reverse("simulation:detail", args=[run.id])).status_code == 200
