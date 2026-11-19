"""Request access (accounts/access_requests.py): the public form, the site
administrator's review page, and what approving or declining does."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessRequest, AccessRequestStatus, Invitation, Profile, Role, Workspace
from audit.models import AuditAction, AuditEvent
from conftest import PASSWORD
from core.notifications import notifications_for

pytestmark = pytest.mark.django_db
User = get_user_model()
FORM = reverse("accounts:request_access")
REVIEW = reverse("settings:access_requests")


@pytest.fixture(autouse=True)
def closed(settings):
    settings.CODEGUARD_REGISTRATION = "closed"


@pytest.fixture
def site_admin(db):
    return User.objects.create_superuser("root", "root@example.com", PASSWORD)


@pytest.fixture
def site_client(site_admin):
    client = Client()
    client.force_login(site_admin)
    return client


def ask(client, **overrides):
    data = {
        "name": "Grace Hopper",
        "email": "Grace@Example.org",
        "organization": "Navy Labs",
        "reason": "Teaching supply chain risk.\nSecond line.",
        **overrides,
    }
    return client.post(FORM, data)


def approve(client, access, **overrides):
    data = {"workspace": "new", "workspace_name": access.organization, "role": Role.ADMIN, **overrides}
    return client.post(
        reverse("settings:approve_access_request", args=[access.pk]),
        {f"a{access.pk}-{key}": value for key, value in data.items()},
    )


# --- The public form ----------------------------------------------------------------


def test_a_request_is_stored_audited_and_sent_to_site_admins(
    client, site_admin, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = ask(client)
    assert response.status_code == 302 and response.url == reverse("accounts:request_access_sent")
    access = AccessRequest.objects.get()
    assert (access.email, access.organization, access.status) == ("grace@example.org", "Navy Labs", "pending")
    event = AuditEvent.objects.get(action=AuditAction.ACCESS_REQUEST)
    assert event.workspace is None and "grace" not in str(event.metadata).lower()  # only a keyed hash
    assert [m.to for m in mailoutbox] == [["root@example.com"]]
    assert "Navy Labs" in mailoutbox[0].body and REVIEW in mailoutbox[0].body
    page = client.get(response.url).content.decode()
    assert "Request received" in page and "grace@example.org" in page


def test_no_email_backend_means_no_email_but_the_request_still_counts(
    client, site_admin, settings, mailoutbox, django_capture_on_commit_callbacks
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    with django_capture_on_commit_callbacks(execute=True):
        ask(client)
    assert AccessRequest.objects.count() == 1 and mailoutbox == []


def test_asking_twice_keeps_one_request_and_reveals_nothing(client, analyst):
    first = ask(client)
    second = ask(client, email="grace@example.org", reason="again")
    assert first.url == second.url
    assert AccessRequest.objects.count() == 1
    assert AccessRequest.objects.get().reason.startswith("Teaching")
    # An address that already has an account gets the same page too.
    assert ask(client, email=analyst.email).url == first.url


def test_required_fields_and_the_honeypot(client):
    response = ask(client, name="", organization="")
    assert response.status_code == 200
    assert set(response.context["form"].errors) == {"name", "organization"}
    assert ask(client, website="http://spam.example").status_code == 302
    assert not AccessRequest.objects.exists()


def test_one_network_is_limited_to_five_requests_an_hour(client):
    for n in range(5):
        assert ask(client, email=f"p{n}@example.org").status_code == 302
    response = ask(client, email="p9@example.org")
    assert response.status_code == 200 and "Too many requests" in response.content.decode()
    assert AccessRequest.objects.count() == 5


def test_the_form_steps_aside_when_sign_up_is_open_or_you_are_signed_in(client, analyst, settings):
    settings.CODEGUARD_REGISTRATION = "open"
    assert client.get(FORM).url == reverse("accounts:register")
    settings.CODEGUARD_REGISTRATION = "closed"
    client.force_login(analyst)
    assert client.get(FORM).status_code == 302 and client.get(FORM).url == reverse("core:start")


def test_public_pages_link_to_the_form_while_sign_up_is_closed(client):
    for name in ("core:landing", "accounts:login", "core:contact", "accounts:register"):
        assert FORM in client.get(reverse(name)).content.decode(), name


# --- Reviewing ----------------------------------------------------------------------


def test_only_site_admins_can_review(admin_client, viewer):
    ask(Client())  # admin_client is the signed-in test client, so ask from another
    access = AccessRequest.objects.get()
    assert admin_client.get(REVIEW).status_code == 403  # a workspace admin, not a site admin
    viewer_client = Client()
    viewer_client.force_login(viewer)
    assert viewer_client.get(REVIEW).status_code == 403
    assert approve(admin_client, access).status_code == 403
    assert admin_client.post(reverse("settings:decline_access_request", args=[access.pk])).status_code == 403
    assert REVIEW not in admin_client.get(reverse("settings:profile")).content.decode()
    assert AccessRequest.objects.get().is_pending


def test_approving_into_a_new_workspace_invites_them_as_its_admin(client, site_client, site_admin, mailoutbox):
    ask(client)
    access = AccessRequest.objects.get()
    page = site_client.get(REVIEW).content.decode()
    assert "Grace Hopper" in page and "Second line." in page and 'value="Navy Labs"' in page
    mailoutbox.clear()

    response = approve(site_client, access)
    assert response.status_code == 302
    access.refresh_from_db()
    assert access.status == AccessRequestStatus.APPROVED and access.reviewed_by == site_admin
    invitation = access.invitation
    assert invitation.workspace.name == "Navy Labs" and invitation.role == Role.ADMIN
    assert invitation.email == "grace@example.org" and invitation.workspace.created_by == site_admin
    assert [m.to for m in mailoutbox] == [["grace@example.org"]]
    # The link is shown once on the review page, for passing on by hand.
    page = site_client.get(REVIEW).content.decode()
    assert "/accounts/invitation/" in page and "Recently reviewed" in page
    assert "/accounts/invitation/" not in site_client.get(REVIEW).content.decode()
    approve_event = AuditEvent.objects.get(action=AuditAction.ACCESS_APPROVE)
    assert approve_event.workspace == invitation.workspace and approve_event.metadata["role"] == "admin"
    # The invitation is accepted like any other.
    token = page.split("/accounts/invitation/")[1].split("/")[0]
    accepted = Client().post(
        reverse("accounts:accept_invitation", args=[token]),
        {
            "first_name": "Grace",
            "username": "grace",
            "password1": PASSWORD,
            "password2": PASSWORD,
            "accept_terms": "on",
        },
    )
    assert accepted.status_code == 302
    profile = Profile.objects.get(user__username="grace")
    assert profile.workspace == invitation.workspace and profile.role == Role.ADMIN


def test_approving_into_an_existing_workspace(client, site_client):
    team = Workspace.objects.create(name="Borealis")
    ask(client)
    access = AccessRequest.objects.get()
    approve(site_client, access, workspace=str(team.pk), workspace_name="", role=Role.VIEWER)
    invitation = Invitation.objects.get()
    assert invitation.workspace == team and invitation.role == Role.VIEWER
    assert Workspace.objects.filter(name="Navy Labs").count() == 0


def test_a_new_workspace_needs_a_name(client, site_client):
    ask(client)
    access = AccessRequest.objects.get()
    response = approve(site_client, access, workspace_name=" ")
    assert response.status_code == 302
    assert AccessRequest.objects.get().is_pending and not Invitation.objects.exists()
    assert "Name the new workspace." in site_client.get(REVIEW).content.decode()


def test_an_address_that_got_an_account_meanwhile_cannot_be_invited(client, site_client):
    ask(client)
    access = AccessRequest.objects.get()
    User.objects.create_user("grace", "grace@example.org", PASSWORD)
    assert "already has an account" in site_client.get(REVIEW).content.decode()
    approve(site_client, access)
    assert AccessRequest.objects.get().is_pending and not Invitation.objects.exists()


def test_declining_closes_it_once(client, site_client):
    ask(client)
    access = AccessRequest.objects.get()
    url = reverse("settings:decline_access_request", args=[access.pk])
    assert site_client.post(url).status_code == 302
    assert AccessRequest.objects.get().status == AccessRequestStatus.DECLINED
    assert AuditEvent.objects.filter(action=AuditAction.ACCESS_DECLINE).count() == 1
    # Reviewed requests can be neither declined nor approved again.
    assert site_client.post(url).status_code == 404
    assert approve(site_client, access).status_code == 404
    assert site_client.get(url).status_code == 405


def test_a_new_request_from_the_same_address_after_a_decision(client, site_client):
    ask(client)
    site_client.post(reverse("settings:decline_access_request", args=[AccessRequest.objects.get().pk]))
    ask(client)
    assert AccessRequest.objects.filter(status=AccessRequestStatus.PENDING).count() == 1


def test_site_admins_are_notified_while_requests_wait(client, site_admin, admin_user):
    ask(client)
    titles = [n.title for n in notifications_for(site_admin)]
    assert "Grace Hopper asked for access" in titles
    assert not any("asked for access" in n.title for n in notifications_for(admin_user))
    AccessRequest.objects.update(status=AccessRequestStatus.DECLINED)
    assert not any("asked for access" in n.title for n in notifications_for(site_admin))


def test_reviewed_requests_are_purged_after_the_retention_period(client, settings):
    settings.CODEGUARD_ACCESS_REQUEST_DAYS = 90
    for email in ("old@example.org", "recent@example.org", "waiting@example.org"):
        ask(client, email=email)
    long_ago = timezone.now() - timedelta(days=91)
    AccessRequest.objects.filter(email="old@example.org").update(status="declined", reviewed_at=long_ago)
    AccessRequest.objects.filter(email="recent@example.org").update(status="approved", reviewed_at=timezone.now())
    AccessRequest.objects.filter(email="waiting@example.org").update(created_at=long_ago)
    call_command("purge_access_requests", verbosity=0)
    assert sorted(AccessRequest.objects.values_list("email", flat=True)) == [
        "recent@example.org",
        "waiting@example.org",
    ]
