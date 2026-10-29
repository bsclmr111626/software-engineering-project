import pytest
from django.urls import reverse

from audit.models import AuditAction, AuditEvent
from audit.services import record_event, sanitize_metadata

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
