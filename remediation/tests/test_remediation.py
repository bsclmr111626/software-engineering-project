import pytest
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from audit.models import AuditAction, AuditEvent
from remediation import services
from remediation.models import RemediationItem, RemediationStatus
from simulation.services import run_simulation
from threats.models import SecurityControl, ThreatScenario

pytestmark = pytest.mark.django_db

SCENARIO = "compromised-developer-account"


def run_for(user, controls=()):
    scenario = ThreatScenario.objects.get(slug=SCENARIO)
    return run_simulation(
        user,
        scenario,
        likelihood=scenario.likelihood,
        severity=scenario.severity,
        impact=scenario.impact,
        threshold=scenario.propagation_threshold,
        controls=SecurityControl.objects.filter(slug__in=controls),
    )


def top_recommendation(run):
    return run.result["recommendations"][0]


def track(client, run, control):
    return client.post(reverse("remediation:track"), {"run": str(run.pk), "control": control})


def test_report_offers_add_to_plan_and_tracking_creates_an_audited_item(seeded, analyst, analyst_client):
    run = run_for(analyst)
    rec = top_recommendation(run)
    page = analyst_client.get(reverse("simulation:detail", args=[run.pk])).content.decode()
    assert "Add to plan" in page

    response = track(analyst_client, run, rec["control"])
    assert response.status_code == 302
    item = RemediationItem.objects.get(owner=analyst)
    assert item.control.slug == rec["control"]
    assert item.source_run == run
    assert item.baseline_risk == run.residual_risk
    assert item.expected_reduction == rec["risk_reduction"]
    assert item.status == RemediationStatus.OPEN
    assert AuditEvent.objects.filter(action=AuditAction.REMEDIATION_CREATE, object_id=str(item.pk)).exists()
    page = analyst_client.get(reverse("simulation:detail", args=[run.pk])).content.decode()
    assert "On your plan: open" in page


def test_tracking_twice_does_not_duplicate(seeded, analyst, analyst_client):
    run = run_for(analyst)
    control = top_recommendation(run)["control"]
    track(analyst_client, run, control)
    track(analyst_client, run, control)
    assert RemediationItem.objects.filter(owner=analyst).count() == 1


def test_database_allows_only_one_active_item_per_control_and_scenario(seeded, analyst):
    run = run_for(analyst)
    item, _ = services.track(analyst, run, top_recommendation(run)["control"])
    with pytest.raises(IntegrityError):
        RemediationItem.objects.create(
            owner=analyst,
            control=item.control,
            scenario_slug=item.scenario_slug,
            scenario_name=item.scenario_name,
            baseline_risk=1,
            expected_reduction=1,
        )


def test_a_closed_item_can_be_tracked_again(seeded, analyst):
    run = run_for(analyst)
    control = top_recommendation(run)["control"]
    item, _ = services.track(analyst, run, control)
    services.update(analyst, item, status=RemediationStatus.RISK_ACCEPTED, note="Accepted by CISO", due_date=None)
    again, created = services.track(analyst, run, control)
    assert created and again.pk != item.pk


def test_only_recommended_controls_can_be_tracked(seeded, analyst, analyst_client):
    run = run_for(analyst)
    recommended = {r["control"] for r in run.result["recommendations"]}
    not_recommended = SecurityControl.objects.exclude(slug__in=recommended).first()
    track(analyst_client, run, not_recommended.slug)
    track(analyst_client, run, "no-such-control")
    assert not RemediationItem.objects.exists()


def test_viewers_cannot_track_and_strangers_cannot_reach_private_runs(seeded, analyst, other_analyst, viewer):
    run = run_for(analyst)
    control = top_recommendation(run)["control"]
    viewer_client = Client()
    viewer_client.force_login(viewer)
    assert track(viewer_client, run, control).status_code == 403
    other = Client()
    other.force_login(other_analyst)
    assert track(other, run, control).status_code == 404  # private run: not disclosed
    assert not RemediationItem.objects.exists()


def test_items_are_private_to_their_owner(seeded, analyst, other_analyst, admin_user):
    run = run_for(analyst)
    item, _ = services.track(analyst, run, top_recommendation(run)["control"])
    for user in (other_analyst, admin_user):
        client = Client()
        client.force_login(user)
        assert client.get(reverse("remediation:detail", args=[item.pk])).status_code == 404
        assert client.post(reverse("remediation:detail", args=[item.pk]), {"status": "done"}).status_code == 404
        assert item.control.name not in client.get(reverse("remediation:plan")).content.decode()


def test_update_sets_and_clears_closed_at_and_is_audited(seeded, analyst, analyst_client):
    run = run_for(analyst)
    item, _ = services.track(analyst, run, top_recommendation(run)["control"])
    url = reverse("remediation:detail", args=[item.pk])
    response = analyst_client.post(url, {"status": "done", "due_date": "2026-12-01", "note": "Rolled out to all repos"})
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.status == RemediationStatus.DONE and item.closed_at is not None
    assert str(item.due_date) == "2026-12-01" and item.note == "Rolled out to all repos"
    analyst_client.post(url, {"status": "in_progress", "due_date": "", "note": ""})
    item.refresh_from_db()
    assert item.closed_at is None
    changes = AuditEvent.objects.filter(action=AuditAction.REMEDIATION_UPDATE, object_id=str(item.pk))
    assert [e.metadata["new_status"] for e in changes.order_by("created_at", "id")] == ["done", "in_progress"]


def test_invalid_status_is_rejected(seeded, analyst, analyst_client):
    run = run_for(analyst)
    item, _ = services.track(analyst, run, top_recommendation(run)["control"])
    response = analyst_client.post(reverse("remediation:detail", args=[item.pk]), {"status": "deleted"})
    assert response.status_code == 200
    assert response.context["form"].errors["status"]
    item.refresh_from_db()
    assert item.status == RemediationStatus.OPEN


def test_verification_needs_a_later_run_with_the_control_enabled(seeded, analyst, analyst_client):
    run = run_for(analyst)
    control = top_recommendation(run)["control"]
    item, _ = services.track(analyst, run, control)
    assert services.verification(item) is None
    run_for(analyst)  # re-run without the control: not a verification
    assert services.verification(item) is None
    confirming = run_for(analyst, controls=[control])
    assert services.verification(item) == confirming
    assert confirming.residual_risk < item.baseline_risk
    page = analyst_client.get(reverse("remediation:plan")).content.decode()
    assert f"Re-run {confirming.short_id}" in page


def test_plan_filters_by_status(seeded, analyst, analyst_client):
    run = run_for(analyst)
    recs = run.result["recommendations"][:2]
    first, _ = services.track(analyst, run, recs[0]["control"])
    second, _ = services.track(analyst, run, recs[1]["control"])
    services.update(analyst, second, status=RemediationStatus.DONE, note="", due_date=None)
    active = analyst_client.get(reverse("remediation:plan")).context["page_obj"]
    assert [i.pk for i in active] == [first.pk]
    done = analyst_client.get(reverse("remediation:plan"), {"status": "done"}).context["page_obj"]
    assert [i.pk for i in done] == [second.pk]
    everything = analyst_client.get(reverse("remediation:plan"), {"status": "bogus"})
    assert everything.status_code == 200  # unknown filter falls back to the default
