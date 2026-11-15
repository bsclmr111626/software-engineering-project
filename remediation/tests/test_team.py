"""Remediation as team work: assignment, sharing with the workspace, evidence,
history, comments, the plan's scopes and the assignee's notifications."""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, Role, Workspace
from accounts.preferences import preferences_for
from audit.models import AuditAction, AuditEvent
from conftest import PASSWORD
from core.notifications import notifications_for
from remediation import services
from remediation.models import ActivityKind, RemediationItem
from remediation.tests.test_remediation import run_for, top_recommendation

pytestmark = pytest.mark.django_db
User = get_user_model()


def client_for(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def item(seeded, analyst):
    run = run_for(analyst)
    tracked, _ = services.track(analyst, run, top_recommendation(run)["control"])
    return tracked


def assign(client, item, assignee=None, shared=False):
    data = {"assignee": assignee.pk if assignee else ""}
    if shared:
        data["is_shared"] = "on"
    return client.post(reverse("remediation:assign", args=[item.pk]), data)


def detail(client, item):
    return client.get(reverse("remediation:detail", args=[item.pk]))


def test_new_items_belong_to_the_owners_workspace_and_start_a_history(item, analyst):
    assert item.workspace == analyst.profile.workspace
    assert not item.is_shared and item.assignee is None
    assert [e.kind for e in item.activity.all()] == [ActivityKind.CREATED]


def test_owner_assigns_a_colleague_who_can_then_see_and_update_it(
    item, analyst, other_analyst, mailoutbox, django_capture_on_commit_callbacks
):
    owner = client_for(analyst)
    with django_capture_on_commit_callbacks(execute=True):
        response = assign(owner, item, other_analyst)
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.assignee == other_analyst and not item.is_shared
    assert item.activity.filter(kind=ActivityKind.ASSIGNEE, new_value="bob").exists()
    event = AuditEvent.objects.get(action=AuditAction.REMEDIATION_ASSIGN)
    assert event.metadata["assignee"] == "bob" and event.actor == analyst
    assert len(mailoutbox) == 1 and mailoutbox[0].to == ["bob@example.com"]
    assert f"/remediation/{item.pk}/" in mailoutbox[0].body

    colleague = client_for(other_analyst)
    assert detail(colleague, item).status_code == 200
    assert item.control.name in colleague.get(reverse("remediation:plan") + "?scope=assigned").content.decode()
    response = colleague.post(
        reverse("remediation:detail", args=[item.pk]),
        {
            "status": "in_progress",
            "due_date": "",
            "note": "On it",
            "evidence_url": "https://github.com/acme/app/pull/7",
        },
    )
    assert response.status_code == 302
    item.refresh_from_db()
    assert item.status == "in_progress" and item.evidence_url.endswith("/pull/7")
    kinds = list(item.activity.values_list("kind", flat=True))
    assert ActivityKind.STATUS in kinds and ActivityKind.EVIDENCE in kinds and ActivityKind.NOTE in kinds
    # The assignee may do the work but not reassign or share it.
    assign(colleague, item, other_analyst, shared=True)
    item.refresh_from_db()
    assert not item.is_shared


def test_assignee_notification_respects_the_preference(
    item, analyst, other_analyst, mailoutbox, django_capture_on_commit_callbacks
):
    prefs = preferences_for(other_analyst)
    prefs.notify_remediation_due = False
    prefs.save()
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        assign(client_for(analyst), item, other_analyst)
    assert len(callbacks) == 1  # the email step ran and chose not to send
    assert mailoutbox == []
    other_analyst._cg_preferences = None
    prefs.notify_remediation_due = True
    prefs.save()
    titles = [n.title for n in notifications_for(other_analyst)]
    assert any("assigned you" in t for t in titles)


def test_unshared_items_stay_private_to_owner_and_assignee(item, analyst, other_analyst, viewer, admin_user):
    for user in (other_analyst, viewer, admin_user):
        assert detail(client_for(user), item).status_code == 404


def test_shared_items_are_visible_to_the_workspace_but_editable_only_by_the_right_people(
    item, analyst, other_analyst, viewer, admin_user
):
    assign(client_for(analyst), item, shared=True)
    item.refresh_from_db()
    assert item.is_shared
    assert item.activity.filter(kind=ActivityKind.SHARING).exists()
    # A colleague can read and comment, but not change it.
    colleague = client_for(other_analyst)
    page = detail(colleague, item)
    assert page.status_code == 200 and b"Save changes" not in page.content
    colleague.post(reverse("remediation:detail", args=[item.pk]), {"status": "done", "note": ""})
    item.refresh_from_db()
    assert item.status == "open"
    colleague.post(reverse("remediation:comment", args=[item.pk]), {"comment": "Happy to help with this."})
    assert item.activity.filter(kind=ActivityKind.COMMENT, actor=other_analyst).exists()
    assert AuditEvent.objects.filter(action=AuditAction.REMEDIATION_COMMENT, actor=other_analyst).exists()
    # Viewers read and comment too.
    assert detail(client_for(viewer), item).status_code == 200
    # A workspace administrator can change and assign it.
    admin = client_for(admin_user)
    assign(admin, item, other_analyst, shared=True)
    item.refresh_from_db()
    assert item.assignee == other_analyst
    admin.post(reverse("remediation:detail", args=[item.pk]), {"status": "risk_accepted", "note": "Accepted"})
    item.refresh_from_db()
    assert item.status == "risk_accepted" and item.closed_at is not None
    # The team scope shows it to everyone who can see it.
    assert item.control.name in colleague.get(reverse("remediation:plan") + "?scope=team&status=all").content.decode()
    assert item.control.name not in client_for(viewer).get(reverse("remediation:plan")).content.decode()


def test_viewers_and_suspended_people_cannot_be_assigned(item, analyst, viewer, other_analyst):
    owner = client_for(analyst)
    assign(owner, item, viewer)
    item.refresh_from_db()
    assert item.assignee is None
    other_analyst.is_active = False
    other_analyst.save()
    assign(owner, item, other_analyst)
    item.refresh_from_db()
    assert item.assignee is None
    with pytest.raises(services.RemediationError):
        services.assign(analyst, item, assignee=viewer, is_shared=False)


def test_nothing_crosses_into_another_workspace(item, analyst):
    borealis = Workspace.objects.create(name="Borealis")
    bea = User.objects.create_user("bea", "bea@example.com", PASSWORD)
    Profile.objects.filter(user=bea).update(workspace=borealis, role=Role.ADMIN)
    bea = User.objects.get(pk=bea.pk)
    owner = client_for(analyst)
    # Cannot be assigned to someone in another workspace...
    assign(owner, item, bea)
    item.refresh_from_db()
    assert item.assignee is None
    # ...and a shared item is invisible there, even to its administrator.
    assign(owner, item, shared=True)
    outsider = client_for(bea)
    assert detail(outsider, item).status_code == 404
    assert outsider.post(reverse("remediation:comment", args=[item.pk]), {"comment": "x"}).status_code == 404
    assert outsider.post(reverse("remediation:assign", args=[item.pk]), {"assignee": bea.pk}).status_code == 404
    page = outsider.get(reverse("remediation:plan") + "?scope=team&status=all").content.decode()
    assert item.control.name not in page
    # Even a stale assignment from before a move does not leak the item.
    RemediationItem.objects.filter(pk=item.pk).update(assignee=bea)
    assert detail(outsider, item).status_code == 404


def test_evidence_must_be_a_web_link(item, analyst):
    owner = client_for(analyst)
    response = owner.post(
        reverse("remediation:detail", args=[item.pk]),
        {"status": "open", "note": "", "evidence_url": "javascript:alert(1)"},
    )
    assert response.status_code == 200
    item.refresh_from_db()
    assert item.evidence_url == ""


def test_overdue_filter_and_assignee_due_dates(item, analyst, other_analyst):
    yesterday = timezone.localdate() - timezone.timedelta(days=1)
    RemediationItem.objects.filter(pk=item.pk).update(due_date=yesterday, assignee=other_analyst)
    owner = client_for(analyst)
    page = owner.get(reverse("remediation:plan") + "?status=overdue").content.decode()
    assert item.control.name in page and "Overdue" in page
    # The due-date notification goes to the assignee, not the owner.
    assert any(n.category == "remediation" and "Overdue" in n.title for n in notifications_for(other_analyst))
    assert not any("Overdue" in n.title for n in notifications_for(analyst))


def test_verification_counts_the_assignees_re_run(item, analyst, other_analyst):
    RemediationItem.objects.filter(pk=item.pk).update(assignee=other_analyst)
    item.refresh_from_db()
    assert services.verification(item) is None
    rerun = run_for(other_analyst, controls=[item.control.slug])
    assert services.verification(item) == rerun


def test_comment_length_is_limited(item, analyst):
    client_for(analyst).post(reverse("remediation:comment", args=[item.pk]), {"comment": "x" * 2001})
    assert not item.activity.filter(kind=ActivityKind.COMMENT).exists()
