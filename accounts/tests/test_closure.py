"""Closing an account: immediate, reversible for a while, then deleted."""

import io
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts import closure
from accounts.models import Profile
from audit.models import AuditAction, AuditEvent
from conftest import PASSWORD
from simulation.models import SimulationRun
from simulation.services import run_simulation
from threats.models import ThreatScenario

pytestmark = pytest.mark.django_db
User = get_user_model()
URL = reverse("settings:close_account")


def close(client, password=PASSWORD, confirm="on"):
    return client.post(URL, {"current_password": password, "confirm": confirm})


def age_closure(user, days):
    Profile.objects.filter(user=user).update(closed_at=timezone.now() - timedelta(days=days))


class TestClosing:
    def test_needs_the_password_and_the_tick(self, analyst_client, analyst):
        assert "The password is incorrect." in close(analyst_client, password="nope").content.decode()
        assert "Tick the box to confirm." in close(analyst_client, confirm="").content.decode()
        analyst.refresh_from_db()
        assert analyst.is_active and analyst.profile.closed_at is None

    def test_closing_signs_out_everywhere_and_blocks_sign_in(self, analyst_client, analyst):
        other_device = Client()
        other_device.force_login(analyst)
        other_device.get(reverse("core:dashboard"))
        response = close(analyst_client)
        assert response.status_code == 302 and response.url == reverse("core:landing")
        analyst.refresh_from_db()
        assert not analyst.is_active and analyst.profile.closed_at is not None
        assert "_auth_user_id" not in analyst_client.session
        assert other_device.get(reverse("core:dashboard")).status_code == 302
        sign_in = Client().post(reverse("accounts:login"), {"username": "alice", "password": PASSWORD})
        assert sign_in.status_code == 200
        assert AuditEvent.objects.filter(action=AuditAction.ACCOUNT_CLOSE, actor_username="alice").exists()

    def test_nothing_is_deleted_at_closing(self, seeded, analyst_client, analyst):
        scenario = ThreatScenario.objects.get(slug="malicious-dependency")
        run_simulation(analyst, scenario, likelihood=70, severity=4, impact=4, threshold=50, controls=[])
        close(analyst_client)
        assert SimulationRun.objects.filter(user=analyst).count() == 1

    def test_page_says_what_will_be_deleted(self, seeded, analyst_client, analyst):
        scenario = ThreatScenario.objects.get(slug="malicious-dependency")
        run = run_simulation(analyst, scenario, likelihood=70, severity=4, impact=4, threshold=50, controls=[])
        SimulationRun.objects.filter(pk=run.pk).update(is_shared=True)
        html = analyst_client.get(URL).content.decode()
        assert "1 simulation run" in html and "including 1 that other people can currently read" in html

    def test_superuser_and_only_admin_are_refused(self, admin_client, admin_user, client):
        html = admin_client.get(URL).content.decode()
        assert "only administrator" in html
        close(admin_client)
        admin_user.refresh_from_db()
        assert admin_user.is_active
        root = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        assert "manage.py" in closure.refusal(root)

    def test_an_admin_can_close_when_another_admin_exists(self, admin_client, admin_user):
        User.objects.create_superuser("root", "root@example.com", PASSWORD)
        assert close(admin_client).status_code == 302
        admin_user.refresh_from_db()
        assert not admin_user.is_active

    def test_requires_sign_in(self, client):
        assert client.get(URL).status_code == 302


class TestReopeningAndDeletion:
    def test_admin_reactivation_cancels_deletion(self, analyst_client, analyst, admin_user):
        close(analyst_client)
        admin = Client()
        admin.force_login(admin_user)
        page = admin.get(reverse("settings:user_detail", args=[analyst.pk])).content.decode()
        assert "Closed by the user" in page
        admin.post(reverse("settings:reactivate_user", args=[analyst.pk]))
        analyst.refresh_from_db()
        assert analyst.is_active and analyst.profile.closed_at is None
        age_closure(analyst, 0)  # no-op guard: a reopened account is never due
        assert not closure.due_for_deletion(0).filter(pk=analyst.pk).exists()

    def test_purge_deletes_only_accounts_past_the_waiting_period(self, seeded, analyst_client, analyst, other_analyst):
        scenario = ThreatScenario.objects.get(slug="malicious-dependency")
        run_simulation(analyst, scenario, likelihood=70, severity=4, impact=4, threshold=50, controls=[])
        close(analyst_client)
        out = io.StringIO()
        call_command("purge_closed_accounts", stdout=out)
        assert "Deleted 0" in out.getvalue() and User.objects.filter(username="alice").exists()

        age_closure(analyst, 15)
        dry = io.StringIO()
        call_command("purge_closed_accounts", "--dry-run", stdout=dry)
        assert "1 closed account(s)" in dry.getvalue() and User.objects.filter(username="alice").exists()

        call_command("purge_closed_accounts", stdout=io.StringIO())
        assert not User.objects.filter(username="alice").exists()
        assert not SimulationRun.objects.exists()
        assert User.objects.filter(username="bob").exists()
        deleted = AuditEvent.objects.get(action=AuditAction.ACCOUNT_DELETE)
        assert deleted.metadata["username"] == "alice" and deleted.metadata["runs"] == 1
        # The record of what the account did survives, under its username.
        assert AuditEvent.objects.filter(action=AuditAction.ACCOUNT_CLOSE, actor_username="alice", actor=None).exists()

    def test_suspended_accounts_are_never_purged(self, admin_client, analyst):
        admin_client.post(reverse("settings:suspend_user", args=[analyst.pk]))
        call_command("purge_closed_accounts", "--days", "1", stdout=io.StringIO())
        assert User.objects.filter(username="alice").exists()

    def test_days_must_be_positive(self):
        with pytest.raises(CommandError):
            call_command("purge_closed_accounts", "--days", "0", stdout=io.StringIO())
