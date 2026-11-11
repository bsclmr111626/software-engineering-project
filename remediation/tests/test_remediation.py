import pytest
from django.db import IntegrityError
from django.test import Client
from django.urls import reverse

from audit.models import AuditAction, AuditEvent
from code_scans.models import CodeFinding, CodeScan
from remediation import services
from remediation.models import CodeFindingRemediation, RemediationItem, RemediationStatus
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


def create_code_finding(user):
    scan = CodeScan.objects.create(
        owner=user,
        project_name="CodeGuard test project",
        uploaded_filename="source.zip",
        languages=["python"],
        status=CodeScan.Status.COMPLETED,
    )

    return CodeFinding.objects.create(
        scan=scan,
        rule_id="py/command-line-injection",
        rule_name="Command-line injection",
        message="User-controlled input reaches a command execution function.",
        severity=CodeFinding.Severity.CRITICAL,
        file_path="app.py",
        start_line=9,
    )


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


def test_code_finding_tracking_creates_one_audited_remediation(seeded, analyst):
    finding = create_code_finding(analyst)

    item, created = services.track_code_finding(analyst, finding)

    assert created is True
    assert item.finding == finding
    assert item.status == RemediationStatus.OPEN
    assert item.recommendation
    assert CodeFindingRemediation.objects.filter(finding=finding).count() == 1

    assert AuditEvent.objects.filter(
        action=AuditAction.REMEDIATION_CREATE,
        object_id=str(item.pk),
    ).exists()


def test_code_finding_tracking_twice_does_not_duplicate(seeded, analyst):
    finding = create_code_finding(analyst)

    first, created_first = services.track_code_finding(analyst, finding)
    second, created_second = services.track_code_finding(analyst, finding)

    assert created_first is True
    assert created_second is False
    assert first.pk == second.pk
    assert CodeFindingRemediation.objects.filter(finding=finding).count() == 1


def test_code_remediation_update_saves_status_note_and_due_date(seeded, analyst, analyst_client):
    finding = create_code_finding(analyst)
    item, _ = services.track_code_finding(analyst, finding)

    url = reverse("remediation:code_detail", args=[item.pk])

    response = analyst_client.post(
        url,
        {
            "status": "in_progress",
            "due_date": "2026-12-01",
            "note": "Corrective action scheduled.",
        },
    )

    assert response.status_code == 302

    item.refresh_from_db()

    assert item.status == RemediationStatus.IN_PROGRESS
    assert str(item.due_date) == "2026-12-01"
    assert item.note == "Corrective action scheduled."
    assert item.closed_at is None

    response = analyst_client.post(
        url,
        {
            "status": "done",
            "due_date": "2026-12-01",
            "note": "Review completed.",
        },
    )

    assert response.status_code == 302

    item.refresh_from_db()

    assert item.status == RemediationStatus.DONE
    assert item.closed_at is not None

    changes = AuditEvent.objects.filter(
        action=AuditAction.REMEDIATION_UPDATE,
        object_id=str(item.pk),
    )

    assert changes.count() == 2


def test_code_remediation_is_private_to_scan_owner(seeded, analyst, other_analyst, admin_user):
    finding = create_code_finding(analyst)
    item, _ = services.track_code_finding(analyst, finding)

    for user in (other_analyst, admin_user):
        client = Client()
        client.force_login(user)

        assert client.get(reverse("remediation:code_detail", args=[item.pk])).status_code == 404

        assert (
            client.post(
                reverse("remediation:code_detail", args=[item.pk]),
                {"status": "done", "note": "Unauthorized"},
            ).status_code
            == 404
        )


def test_code_remediation_appears_on_main_plan(seeded, analyst, analyst_client):
    finding = create_code_finding(analyst)
    item, _ = services.track_code_finding(analyst, finding)

    response = analyst_client.get(reverse("remediation:plan"))

    assert response.status_code == 200
    assert item.pk in [code_item.pk for code_item in response.context["code_page"]]

    page = response.content.decode()

    assert "Code Finding Remediation" in page
    assert "CodeGuard test project" in page
    assert "py/command-line-injection" in page
    assert "Critical" in page
    assert item.status == RemediationStatus.OPEN
    assert item.get_status_display() == "Open"
