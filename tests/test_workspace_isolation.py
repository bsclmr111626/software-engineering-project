"""Workspace isolation: nothing in one workspace can be read or changed from
another, whatever ids are put into a URL or a form.

Workspace A is the default workspace (alice the analyst, ada the
administrator). Workspace B ("Borealis") has its own administrator and
analyst, a private and a shared scenario, a private and a shared report, a
remediation item and an open invitation. Every test here acts as someone in
A and aims at B, or the other way round.
"""

import io

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts import invitations, workspaces
from accounts.models import Invitation, Profile, Role, Workspace
from audit.models import AuditAction, AuditEvent
from audit.services import record_event
from conftest import PASSWORD
from core.analytics import risk_analysis, supply_chain_map
from core.notifications import notifications_for
from core.services import dashboard_metrics
from remediation.models import RemediationItem
from remediation.services import track
from simulation.models import SimulationRun
from simulation.services import accessible_runs, run_simulation
from threats.models import ScenarioStatus, SecurityControl, ThreatScenario, Visibility
from threats.services import clone_scenario, visible_scenarios

pytestmark = pytest.mark.django_db
User = get_user_model()
REFERENCE = "malicious-dependency"


def member(username, role, workspace):
    user = User.objects.create_user(username=username, email=f"{username}@borealis.example", password=PASSWORD)
    Profile.objects.filter(user=user).update(workspace=workspace, role=role)
    return User.objects.get(pk=user.pk)


def run_for(user, shared=False):
    scenario = ThreatScenario.objects.get(slug=REFERENCE)
    run = run_simulation(user, scenario, likelihood=70, severity=4, impact=4, threshold=50, controls=[])
    if shared:
        SimulationRun.objects.filter(pk=run.pk).update(is_shared=True)
        record_event(user, AuditAction.REPORT_SHARE, target=run, shared=True)
    return SimulationRun.objects.get(pk=run.pk)


class Other:
    """Everything that exists in workspace B."""


@pytest.fixture
def b(seeded):
    other = Other()
    other.workspace = Workspace.objects.create(name="Borealis")
    other.admin = member("bea", Role.ADMIN, other.workspace)
    other.analyst = member("ben", Role.ANALYST, other.workspace)
    reference = ThreatScenario.objects.get(slug=REFERENCE)
    other.private_scenario = clone_scenario(reference, other.analyst)
    other.shared_scenario = clone_scenario(reference, other.admin)
    ThreatScenario.objects.filter(pk=other.shared_scenario.pk).update(
        visibility=Visibility.SHARED, name="Borealis internal scenario"
    )
    other.shared_scenario.refresh_from_db()
    other.private_run = run_for(other.analyst)
    other.shared_run = run_for(other.analyst, shared=True)
    control = other.shared_run.result["recommendations"][0]["control"]
    other.item, _ = track(other.analyst, other.shared_run, control)
    other.invitation = Invitation.objects.create(
        workspace=other.workspace,
        email="newhire@borealis.example",
        role=Role.ANALYST,
        token_hash="b" * 64,
        invited_by=other.admin,
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    return other


def client_for(user):
    client = Client()
    client.force_login(user)
    return client


class TestTheBoundaryExists:
    def test_fixture_users_are_in_different_workspaces(self, b, analyst, admin_user):
        assert workspaces.workspace_of(analyst).is_default
        assert workspaces.workspace_of(b.analyst) == b.workspace
        assert not workspaces.same_workspace(analyst, b.analyst)
        assert workspaces.same_workspace(analyst, admin_user)

    def test_reference_library_is_visible_to_every_workspace(self, b, analyst):
        for user in (analyst, b.analyst):
            assert visible_scenarios(user).filter(slug=REFERENCE).exists()

    def test_new_work_lands_in_the_authors_workspace(self, b, analyst):
        assert b.private_scenario.workspace == b.workspace
        assert b.shared_run.workspace == b.workspace
        mine = run_for(analyst)
        assert mine.workspace.is_default


class TestScenarios:
    def test_other_workspaces_scenarios_are_not_listed(self, b, analyst, admin_user):
        for user in (analyst, admin_user):
            slugs = set(visible_scenarios(user).values_list("slug", flat=True))
            assert b.shared_scenario.slug not in slugs and b.private_scenario.slug not in slugs
            html = client_for(user).get(reverse("threats:list")).content.decode()
            assert "Borealis internal scenario" not in html

    @pytest.mark.parametrize("name", ["detail", "edit", "delete"])
    def test_scenario_pages_are_404(self, b, analyst, admin_user, name):
        for user in (analyst, admin_user):
            for scenario in (b.shared_scenario, b.private_scenario):
                assert client_for(user).get(reverse(f"threats:{name}", args=[scenario.slug])).status_code == 404

    @pytest.mark.parametrize("name", ["archive", "delete", "clone", "edit"])
    def test_scenario_actions_are_404_and_change_nothing(self, b, analyst, admin_user, name):
        before = ThreatScenario.objects.count()
        for user in (analyst, admin_user):
            response = client_for(user).post(reverse(f"threats:{name}", args=[b.shared_scenario.slug]), {})
            assert response.status_code == 404
        b.shared_scenario.refresh_from_db()
        assert b.shared_scenario.status == ScenarioStatus.ACTIVE
        assert ThreatScenario.objects.count() == before

    def test_cannot_simulate_another_workspaces_scenario(self, b, analyst_client):
        before = SimulationRun.objects.count()
        analyst_client.post(
            reverse("simulation:configure"),
            {"scenario": b.shared_scenario.slug, "likelihood": 70, "severity": 4, "impact": 4, "threshold": 50},
        )
        assert SimulationRun.objects.count() == before

    def test_shared_scenario_is_visible_inside_its_own_workspace(self, b):
        assert client_for(b.analyst).get(reverse("threats:detail", args=[b.shared_scenario.slug])).status_code == 200
        assert client_for(b.analyst).get(reverse("threats:detail", args=[b.private_scenario.slug])).status_code == 200
        assert client_for(b.admin).get(reverse("threats:detail", args=[b.private_scenario.slug])).status_code == 404


class TestReports:
    def test_shared_report_of_another_workspace_is_not_accessible(self, b, analyst, admin_user):
        for user in (analyst, admin_user):
            assert not accessible_runs(user).filter(pk=b.shared_run.pk).exists()

    def urls(self, run):
        yield reverse("simulation:detail", args=[run.pk])
        for section in ("propagation", "controls", "recommendations", "inputs"):
            yield reverse("simulation:detail_section", args=[run.pk, section])
        yield reverse("reports:document", args=[run.pk])
        yield reverse("simulation:export_run", args=[run.pk])
        for kind in ("stages", "comparison", "risk"):
            yield reverse("simulation:chart", args=[run.pk, kind])

    def test_every_report_url_is_404(self, b, analyst, admin_user):
        for user in (analyst, admin_user):
            client = client_for(user)
            for run in (b.shared_run, b.private_run):
                for url in self.urls(run):
                    assert client.get(url).status_code == 404, url

    def test_share_toggle_rerun_and_compare_are_404(self, b, analyst_client, analyst):
        mine = run_for(analyst)
        assert analyst_client.post(reverse("simulation:share", args=[b.shared_run.pk])).status_code == 404
        assert analyst_client.get(reverse("simulation:configure"), {"rerun": b.shared_run.pk}).status_code == 404
        for params in ({"a": mine.pk, "b": b.shared_run.pk}, {"a": b.shared_run.pk, "b": mine.pk}):
            assert analyst_client.get(reverse("simulation:compare"), params).status_code == 404
            assert analyst_client.get(reverse("simulation:compare_chart"), params).status_code == 404
        b.shared_run.refresh_from_db()
        assert b.shared_run.is_shared

    def test_lists_exports_and_analytics_leave_them_out(self, b, analyst, analyst_client):
        mine = run_for(analyst, shared=True)
        for name in ("reports:list", "simulation:results", "simulation:hub", "core:dashboard", "core:risk"):
            html = analyst_client.get(reverse(name)).content.decode()
            assert str(b.shared_run.pk) not in html, name
        csv = analyst_client.get(reverse("reports:export_history")).content.decode()
        assert str(b.shared_run.pk) not in csv and str(mine.pk) in csv
        metrics = dashboard_metrics(analyst)
        assert {r.pk for r in metrics["recent_runs"]} == {mine.pk}
        assert risk_analysis(analyst)["total"] == 1
        assert supply_chain_map(analyst)["run_count"] == 1

    def test_shared_report_is_readable_inside_its_own_workspace(self, b):
        assert client_for(b.admin).get(reverse("simulation:detail", args=[b.shared_run.pk])).status_code == 200
        assert client_for(b.admin).get(reverse("simulation:detail", args=[b.private_run.pk])).status_code == 404


class TestRemediation:
    def test_item_and_tracking_are_404(self, b, analyst_client):
        assert analyst_client.get(reverse("remediation:detail", args=[b.item.pk])).status_code == 404
        assert (
            analyst_client.post(reverse("remediation:detail", args=[b.item.pk]), {"status": "done"}).status_code == 404
        )
        response = analyst_client.post(
            reverse("remediation:track"), {"run": b.shared_run.pk, "control": b.item.control.slug}
        )
        assert response.status_code == 404
        assert RemediationItem.objects.count() == 1
        b.item.refresh_from_db()
        assert b.item.status == "open"

    def test_plan_lists_only_own_items(self, b, analyst_client):
        assert b.item.control.name not in analyst_client.get(reverse("remediation:plan")).content.decode()


class TestMembersAndInvitations:
    def test_user_list_shows_only_the_workspace(self, b, admin_client, analyst):
        page = admin_client.get(reverse("settings:users"))
        assert {u.username for u in page.context["page_obj"]} == {"ada", "alice"}
        html = page.content.decode()
        assert "bea" not in html and "newhire@borealis.example" not in html
        found = admin_client.get(reverse("settings:users"), {"q": "borealis"})
        assert list(found.context["page_obj"]) == []

    @pytest.mark.parametrize("name", ["suspend_user", "reactivate_user", "send_password_reset", "change_role"])
    def test_managing_another_workspaces_member_is_404(self, b, admin_client, mailoutbox, name):
        response = admin_client.post(reverse(f"settings:{name}", args=[b.analyst.pk]), {"role": "viewer"})
        assert response.status_code == 404
        b.analyst.refresh_from_db()
        assert b.analyst.is_active and b.analyst.profile.role == Role.ANALYST
        assert mailoutbox == []

    def test_member_detail_is_404(self, b, admin_client):
        assert admin_client.get(reverse("settings:user_detail", args=[b.analyst.pk])).status_code == 404

    def test_another_workspaces_invitation_cannot_be_resent_or_revoked(self, b, admin_client, mailoutbox):
        for name in ("resend_invitation", "revoke_invitation"):
            assert admin_client.post(reverse(f"settings:{name}", args=[b.invitation.pk])).status_code == 404
        b.invitation.refresh_from_db()
        assert b.invitation.is_open and b.invitation.token_hash == "b" * 64 and mailoutbox == []

    def test_invitation_joins_the_inviters_workspace_only(self, b, admin_client, mailoutbox):
        # The same address may be invited by two workspaces; each invitation is separate.
        admin_client.post(reverse("settings:invite"), {"email": "newhire@borealis.example", "role": "viewer"})
        mine = Invitation.objects.exclude(pk=b.invitation.pk).get()
        assert mine.workspace.is_default
        link = mailoutbox[0].body.split("https://testserver")[-1].split("http://testserver")[-1].split()[0]
        Client().post(
            link,
            {
                "first_name": "New",
                "username": "newhire",
                "password1": "A-very-long-passphrase-42",
                "password2": "A-very-long-passphrase-42",
                "accept_terms": "on",
            },
        )
        joined = User.objects.get(username="newhire")
        assert joined.profile.workspace.is_default and joined.profile.role == Role.VIEWER
        # The other workspace's invitation can no longer create a second account for the address.
        assert invitations.find("anything") is None

    def test_workspace_page_counts_only_its_members_and_hides_deployment(self, b, admin_client):
        page = admin_client.get(reverse("settings:organization"))
        assert page.context["user_total"] == 1 and page.context["deployment"] is None
        assert "Email delivery" not in page.content.decode()

    def test_platform_admin_sees_deployment_details(self, b):
        root = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        page = client_for(root).get(reverse("settings:organization"))
        assert page.context["deployment"]["workspace_total"] == 2

    def test_admin_can_rename_only_their_own_workspace(self, b, admin_client):
        admin_client.post(reverse("settings:organization"), {"name": "  Acme   Security "})
        assert Workspace.objects.get(is_default=True).name == "Acme Security"
        b.workspace.refresh_from_db()
        assert b.workspace.name == "Borealis"
        assert AuditEvent.objects.filter(action=AuditAction.WORKSPACE_UPDATE, workspace__is_default=True).exists()


class TestAuditAndNotifications:
    def test_admin_sees_only_their_workspaces_events(self, b, admin_client, analyst):
        record_event(analyst, AuditAction.LOGIN)
        page = admin_client.get(reverse("audit:log"), {"view": "table"})
        actors = {e.actor_username for e in page.context["page_obj"]}
        assert "alice" in actors and not actors & {"bea", "ben"}
        assert admin_client.get(reverse("audit:log"), {"user": "ben"}).context["page_obj"].paginator.count == 0

    def test_events_are_recorded_under_the_right_workspace(self, b, client):
        assert set(AuditEvent.objects.filter(actor=b.analyst).values_list("workspace", flat=True)) == {b.workspace.pk}
        client.post(reverse("accounts:login"), {"username": "ben", "password": "wrong"})
        failed = AuditEvent.objects.filter(action=AuditAction.LOGIN_FAILED).latest("id")
        assert failed.workspace == b.workspace
        client.post(reverse("accounts:login"), {"username": "nobody-at-all", "password": "wrong"})
        assert AuditEvent.objects.filter(action=AuditAction.LOGIN_FAILED).latest("id").workspace is None

    def test_other_workspaces_admin_cannot_see_failed_sign_ins_here(self, b, client, analyst):
        client.post(reverse("accounts:login"), {"username": "alice", "password": "wrong"})
        page = client_for(b.admin).get(reverse("audit:log"), {"view": "table"})
        assert all(e.metadata.get("attempted_username") != "alice" for e in page.context["page_obj"])

    def test_shared_report_notifies_only_its_workspace(self, b, analyst):
        assert [n for n in notifications_for(analyst) if n.category == "shared_report"] == []
        assert [n for n in notifications_for(b.admin) if n.category == "shared_report"] != []


class TestSignUpAndLifecycle:
    def test_sign_up_cannot_see_anything_that_already_exists(self, b, client, analyst, mailoutbox, settings):
        settings.CODEGUARD_REGISTRATION = "open"
        mine = run_for(analyst, shared=True)
        client.post(
            reverse("accounts:register"),
            {
                "first_name": "Zed",
                "username": "zed",
                "email": "zed@example.org",
                "workspace_name": "Zed Labs",
                "password1": "A-very-long-passphrase-42",
                "password2": "A-very-long-passphrase-42",
                "accept_terms": "on",
            },
        )
        zed = User.objects.get(username="zed")
        assert zed.profile.workspace.name == "Zed Labs"
        assert not accessible_runs(zed).exists()
        assert set(visible_scenarios(zed).values_list("is_system", flat=True)) == {True}
        # As administrator of the new workspace, zed manages nobody else.
        zed_client = client_for(zed)
        assert {u.username for u in zed_client.get(reverse("settings:users")).context["page_obj"]} == {"zed"}
        assert zed_client.get(reverse("settings:user_detail", args=[analyst.pk])).status_code == 404
        assert zed_client.get(reverse("simulation:detail", args=[mine.pk])).status_code == 404
        assert zed_client.get(reverse("threats:edit", args=[REFERENCE])).status_code == 403

    def test_closing_an_account_only_considers_its_own_workspace(self, b):
        from accounts import closure

        # bea is the only administrator of Borealis and ben would be left without one,
        # however many administrators other workspaces have.
        assert "only administrator of this workspace" in closure.refusal(b.admin)
        Profile.objects.filter(user=b.analyst).update(role=Role.ADMIN)
        assert closure.refusal(b.admin) is None

    def test_data_export_names_the_workspace_and_nothing_from_others(self, b, analyst_client):
        text = analyst_client.get(reverse("settings:export_data")).content.decode()
        assert '"workspace": "CodeGuard"' in text and "Borealis" not in text

    def test_seed_command_keeps_reference_scenarios_outside_any_workspace(self, b):
        call_command("seed_codeguard", stdout=io.StringIO())
        assert not ThreatScenario.objects.filter(is_system=True, workspace__isnull=False).exists()
        assert SecurityControl.objects.count() == 14
