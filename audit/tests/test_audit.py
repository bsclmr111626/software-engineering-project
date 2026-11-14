import pytest
from django.urls import reverse

from audit.models import AuditAction, AuditEvent
from audit.services import client_ip, record_event, sanitize_metadata

pytestmark = pytest.mark.django_db


def test_sensitive_metadata_is_removed():
    clean = sanitize_metadata(
        {"password": "x", "api_token": "y", "sessionid": "z", "csrfmiddlewaretoken": "c", "scenario": "ok"}
    )
    assert clean == {"scenario": "ok"}


def test_long_values_are_truncated():
    assert len(sanitize_metadata({"note": "a" * 5000})["note"]) == 200


def test_record_event_stores_safe_context(analyst):
    event = record_event(analyst, AuditAction.SCENARIO_CREATE, target=analyst, password="secret", detail="v1")
    assert event.actor_username == "alice"
    assert event.metadata == {"detail": "v1"}
    assert event.object_type == "User"


def test_events_are_append_only(analyst):
    event = record_event(analyst, AuditAction.LOGIN)
    event.action = AuditAction.LOGOUT
    with pytest.raises(ValueError):
        event.save()


def test_events_survive_user_deletion(analyst):
    record_event(analyst, AuditAction.LOGIN)
    analyst.delete()
    event = AuditEvent.objects.get()
    assert event.actor is None
    assert event.actor_username == "alice"


def test_non_admin_sees_only_own_events(analyst, other_analyst, analyst_client):
    record_event(analyst, AuditAction.SCENARIO_CREATE)
    record_event(other_analyst, AuditAction.SCENARIO_CREATE)
    response = analyst_client.get(reverse("audit:log"))
    usernames = {e.actor_username for e in response.context["page_obj"]}
    assert usernames == {"alice"}
    assert not response.context["show_all"]


def test_admin_sees_all_events_and_can_filter(analyst, other_analyst, admin_client):
    record_event(analyst, AuditAction.SCENARIO_CREATE)
    record_event(other_analyst, AuditAction.SIMULATION_RUN)
    response = admin_client.get(reverse("audit:log"))
    assert {"alice", "bob"} <= {e.actor_username for e in response.context["page_obj"]}
    response = admin_client.get(reverse("audit:log"), {"action": "simulation_run"})
    assert [e.actor_username for e in response.context["page_obj"]] == ["bob"]
    response = admin_client.get(reverse("audit:log"), {"user": "ali"})
    assert {e.actor_username for e in response.context["page_obj"]} == {"alice"}


def test_scenario_actions_are_audited(seeded, analyst, analyst_client):
    analyst_client.post(reverse("threats:clone", args=["malicious-dependency"]))
    event = AuditEvent.objects.get(action=AuditAction.SCENARIO_CLONE)
    assert event.metadata == {"source": "malicious-dependency"}


def test_bulk_update_and_delete_are_refused(analyst):
    event = record_event(analyst, AuditAction.LOGIN)
    with pytest.raises(ValueError):
        AuditEvent.objects.filter(pk=event.pk).update(action=AuditAction.LOGOUT)
    with pytest.raises(ValueError):
        AuditEvent.objects.filter(pk=event.pk).delete()
    with pytest.raises(ValueError):
        event.delete()
    assert AuditEvent.objects.get(pk=event.pk).action == AuditAction.LOGIN


def test_deleting_a_user_keeps_their_events(analyst):
    event = record_event(analyst, AuditAction.LOGIN)
    analyst.delete()
    event = AuditEvent.objects.get(pk=event.pk)
    assert event.actor is None
    assert event.actor_username == "alice"


def test_retention_purge(analyst):
    from datetime import timedelta
    from unittest import mock

    from django.core.management import CommandError, call_command
    from django.utils import timezone

    old_time = timezone.now() - timedelta(days=400)
    with mock.patch("django.utils.timezone.now", return_value=old_time):
        old = record_event(analyst, AuditAction.LOGIN)
    recent = record_event(analyst, AuditAction.LOGOUT)
    call_command("purge_audit_events", "--days", "365", "--dry-run")
    assert AuditEvent.objects.filter(pk=old.pk).exists()
    call_command("purge_audit_events", "--days", "365")
    assert not AuditEvent.objects.filter(pk=old.pk).exists()
    assert AuditEvent.objects.filter(pk=recent.pk).exists()
    purge = AuditEvent.objects.get(action=AuditAction.AUDIT_PURGE)
    assert purge.metadata == {"retention_days": 365, "deleted": 1}
    with pytest.raises(CommandError):
        call_command("purge_audit_events", "--days", "7")


class TestClientIp:
    """audit.services.client_ip: REMOTE_ADDR unless a trusted proxy header is configured."""

    def get(self, rf, **meta):
        return rf.get("/", REMOTE_ADDR="10.0.0.9", **meta)

    def test_forwarding_headers_are_ignored_by_default(self, rf):
        request = self.get(rf, HTTP_X_REAL_IP="203.0.113.5", HTTP_X_FORWARDED_FOR="203.0.113.5")
        assert client_ip(request) == "10.0.0.9"

    def test_configured_header_is_used(self, rf, settings):
        settings.CODEGUARD_CLIENT_IP_META_KEY = "HTTP_X_REAL_IP"
        assert client_ip(self.get(rf, HTTP_X_REAL_IP="203.0.113.5")) == "203.0.113.5"

    def test_last_entry_of_a_forwarding_list_is_used(self, rf, settings):
        settings.CODEGUARD_CLIENT_IP_META_KEY = "HTTP_X_FORWARDED_FOR"
        request = self.get(rf, HTTP_X_FORWARDED_FOR="198.51.100.1, 203.0.113.5")
        assert client_ip(request) == "203.0.113.5"

    @pytest.mark.parametrize("value", ["", "not-an-address", "203.0.113.5<script>"])
    def test_missing_or_invalid_header_falls_back(self, rf, settings, value):
        settings.CODEGUARD_CLIENT_IP_META_KEY = "HTTP_X_REAL_IP"
        assert client_ip(self.get(rf, HTTP_X_REAL_IP=value)) == "10.0.0.9"

    def test_sign_in_limit_follows_the_configured_header(self, client, settings):
        settings.CODEGUARD_CLIENT_IP_META_KEY = "HTTP_X_REAL_IP"
        url = reverse("accounts:login")
        for i in range(20):
            client.post(url, {"username": f"user{i}", "password": "wrong"}, HTTP_X_REAL_IP="203.0.113.5")
        blocked = client.post(url, {"username": "someone", "password": "wrong"}, HTTP_X_REAL_IP="203.0.113.5")
        assert "Too many failed sign-in attempts" in blocked.content.decode()
        other = client.post(url, {"username": "someone", "password": "wrong"}, HTTP_X_REAL_IP="203.0.113.6")
        assert "Too many failed sign-in attempts" not in other.content.decode()
        assert AuditEvent.objects.filter(ip_address="203.0.113.5").count() >= 20


class TestDatabaseProtection:
    """audit/integrity.py: the database itself refuses to rewrite audit history."""

    def test_protections_are_installed(self, db):
        from audit import integrity

        assert integrity.installed() == {
            "audit_event_no_update",
            "audit_event_no_early_delete",
            "accounts_user_email_ci_unique",
        }

    def test_raw_sql_cannot_edit_an_event(self, analyst):
        from django.db import IntegrityError, connection, transaction

        event = record_event(analyst, AuditAction.LOGIN)
        for sql in (
            "UPDATE audit_auditevent SET action = 'logout' WHERE id = %s",
            "UPDATE audit_auditevent SET actor_username = 'someone' WHERE id = %s",
            "UPDATE audit_auditevent SET ip_address = '1.2.3.4' WHERE id = %s",
        ):
            with pytest.raises(IntegrityError, match="append-only"), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, [event.pk])
        assert AuditEvent.objects.get(pk=event.pk).action == AuditAction.LOGIN

    def test_raw_sql_cannot_delete_a_recent_event(self, analyst):
        from django.db import IntegrityError, connection, transaction

        event = record_event(analyst, AuditAction.LOGIN)
        with pytest.raises(IntegrityError, match="at least 30 days"), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM audit_auditevent WHERE id = %s", [event.pk])
        assert AuditEvent.objects.filter(pk=event.pk).exists()

    def test_install_is_repeatable_and_restores_dropped_protection(self, db):
        from django.db import connection

        from audit import integrity

        with connection.cursor() as cursor:
            cursor.execute("DROP TRIGGER audit_event_no_update")
        assert "audit_event_no_update" not in integrity.installed()
        integrity.install()
        integrity.install()
        assert "audit_event_no_update" in integrity.installed()
