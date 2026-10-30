"""The product areas added by the redesign: their figures come from the database
and respect visibility, and notifications reflect real records."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.preferences import preferences_for
from core import svgcharts
from core.notifications import notifications_for, unread_count
from remediation.models import RemediationItem, RemediationStatus
from simulation.services import run_simulation
from threats.models import SecurityControl, ThreatScenario

pytestmark = pytest.mark.django_db


def _run(user, slug="compromised-cicd-pipeline", controls=()):
    scenario = ThreatScenario.objects.get(slug=slug)
    return run_simulation(user, scenario, likelihood=70, severity=4, impact=4, threshold=50, controls=list(controls))


def test_legacy_dashboard_url_redirects(analyst_client):
    response = analyst_client.get("/dashboard/")
    assert response.status_code == 301 and response.url == reverse("core:dashboard")


def test_supply_chain_map_counts_visible_paths_and_runs(seeded, analyst, other_analyst, analyst_client):
    _run(analyst)
    _run(other_analyst)  # private to bob: must not be counted for alice
    data = analyst_client.get(reverse("core:supply_chain")).context["map"]
    assert len(data["stages"]) == 5
    assert data["run_count"] == 1
    assert data["scenario_count"] == ThreatScenario.objects.filter(visibility="shared", status="active").count()
    assert data["edges"] and all(e["scenarios"] >= 1 for e in data["edges"])
    cicd = next(row for row in data["stages"] if row["stage"].key == "cicd")
    assert cicd["compromised"] == 1 and cicd["assets"]


def test_stage_detail_and_unknown_stage(seeded, analyst_client):
    response = analyst_client.get(reverse("core:stage_detail", args=["cicd"]))
    assert response.status_code == 200
    assert response.context["previous_stage"].key == "vcs" and response.context["next_stage"].key == "registry"
    assert analyst_client.get(reverse("core:stage_detail", args=["nope"])).status_code == 404


def test_risk_analysis_aggregates_and_scopes(seeded, analyst, other_analyst, analyst_client):
    mfa = SecurityControl.objects.get(slug="isolated-builds")
    base, improved = _run(analyst), _run(analyst, controls=[mfa])
    _run(other_analyst)
    analysis = analyst_client.get(reverse("core:risk")).context["analysis"]
    assert analysis["total"] == 2
    assert analysis["residual"] == round((base.residual_risk + improved.residual_risk) / 2, 1)
    assert [r.id for r in analysis["trend_runs"]] == [base.id, improved.id]
    assert analysis["control_rows"][0]["slug"] == "isolated-builds"
    filtered = analyst_client.get(reverse("core:risk"), {"scenario": "no-such"}).context
    assert filtered["analysis"]["total"] == 0 and filtered["scenario"] == ""


def test_risk_analysis_empty_state(seeded, analyst_client):
    assert b"No completed runs in this scope" in analyst_client.get(reverse("core:risk")).content


def _client(user):
    from django.test import Client

    c = Client()
    c.force_login(user)
    return c


def test_simulation_hub_and_results(seeded, analyst, viewer):
    analyst_client, viewer_client = _client(analyst), _client(viewer)
    run = _run(analyst)
    hub = analyst_client.get(reverse("simulation:hub"))
    assert hub.status_code == 200 and hub.context["scenario_count"] == 6
    results = analyst_client.get(reverse("simulation:results"))
    assert list(results.context["page_obj"]) == [run]
    assert viewer_client.get(reverse("simulation:results")).context["page_obj"].paginator.count == 0
    assert b"cannot run simulations" in viewer_client.get(reverse("simulation:hub")).content


@pytest.mark.parametrize("section", ["stages", "paths", "controls", "method"])
def test_result_sections_and_report_document(seeded, analyst, analyst_client, other_analyst, section):
    run = _run(analyst)
    response = analyst_client.get(reverse("simulation:detail_section", args=[run.id, section]))
    assert response.status_code == 200 and response.context["section"] == section
    document = analyst_client.get(reverse("reports:document", args=[run.id]))
    assert document.status_code == 200 and b"Inputs and limitations" in document.content
    assert analyst_client.get(reverse("simulation:detail_section", args=[run.id, "bogus"])).status_code == 404


def test_report_document_is_private(seeded, analyst, client, other_analyst):
    run = _run(analyst)
    client.force_login(other_analyst)
    assert client.get(reverse("reports:document", args=[run.id])).status_code == 404


def test_summary_lists_affected_assets_of_compromised_stages(seeded, analyst, analyst_client):
    run = _run(analyst)
    assets = analyst_client.get(reverse("simulation:detail", args=[run.id])).context["affected_assets"]
    assert {row["stage"].stage_key for row in assets} == {
        s.stage_key for s in run.stage_results.all() if s.state in ("entry", "compromised")
    }
    assert all(row["assets"] for row in assets)


def test_notifications_from_real_records(seeded, analyst, other_analyst, analyst_client):
    assert notifications_for(analyst) == []
    shared = _run(other_analyst)
    analyst_client.logout()
    from django.test import Client

    bob = Client()
    bob.force_login(other_analyst)
    bob.post(reverse("simulation:share", args=[shared.id]))
    mine = _run(analyst)
    rec = mine.result["recommendations"][0]
    RemediationItem.objects.create(
        owner=analyst, control=SecurityControl.objects.get(slug=rec["control"]), scenario_slug=mine.scenario_slug,
        scenario_name=mine.scenario_name, source_run=mine, baseline_risk=mine.residual_risk, expected_reduction=1,
        due_date=timezone.localdate() - timedelta(days=2), status=RemediationStatus.OPEN,
    )  # fmt: skip
    found = notifications_for(analyst)
    assert {n.category for n in found} == {"shared_report", "remediation"}
    assert any("Overdue by 2 days" in n.title for n in found)
    assert unread_count(analyst) == 2

    preferences = preferences_for(analyst)
    preferences.notify_shared_reports = False
    preferences.save()
    assert {n.category for n in notifications_for(analyst)} == {"remediation"}


def test_security_notifications_and_mark_read(seeded, analyst, admin_user):
    analyst_client, admin_client = _client(analyst), _client(admin_user)
    admin_client.post(reverse("settings:change_role", args=[analyst.pk]), {"role": "viewer"})
    titles = [n.title for n in notifications_for(analyst)]
    assert "Your role was changed" in titles
    html = analyst_client.get(reverse("core:dashboard")).content.decode()
    assert 'aria-label="Notifications, 1 unread"' in html
    analyst_client.post(reverse("core:notifications_read"))
    from django.contrib.auth import get_user_model

    assert unread_count(get_user_model().objects.get(pk=analyst.pk)) == 0  # a fresh request's view of the user
    assert analyst_client.get(reverse("core:notifications_read")).status_code == 405


def test_svg_chart_geometry():
    bars = svgcharts.hbars(
        [{"label": "a", "value": 50, "cls": "x", "tip": ""}, {"label": "b", "value": 0, "cls": "x", "tip": ""}],
        width=300,
    )
    assert bars["rows"][0]["w"] == round(0.5 * (300 - 56), 1) and bars["rows"][1]["w"] == 0
    line = svgcharts.line_chart([{"name": "s", "cls": "c", "values": [0, 100, None]}], ["a", "b", "c"])
    assert len(line["series"][0]["points"]) == 2
    assert line["series"][0]["points"][1]["y"] == line["plot_top"]  # 100 sits on the top of the plot
    assert [g["v"] for g in line["guides"]] == [50, 30, 15]
    columns = svgcharts.paired_columns([{"label": "s", "a": 40, "b": None}], height=240)
    assert columns["groups"][0]["bh"] == 0 and columns["groups"][0]["ah"] > 0
