"""The account lifecycle: sign-up with email confirmation, email changes,
password resets, invitations and administrator user management."""

import re
import time
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts import tokens
from accounts.models import AccountOrigin, Invitation, Profile, Role
from accounts.preferences import preferences_for
from audit.models import AuditAction, AuditEvent
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
User = get_user_model()
NEW_PASSWORD = "A-very-long-passphrase-42"


def sign_up(client, **extra):
    data = {
        "first_name": "Nia",
        "last_name": "Otieno",
        "username": "nia",
        "email": "nia@example.com",
        "password1": NEW_PASSWORD,
        "password2": NEW_PASSWORD,
        "accept_terms": "on",
    }
    data.update(extra)
    return client.post(reverse("accounts:register"), data)


def link_in(message, path):
    match = re.search(r"https?://testserver(" + re.escape(path) + r"\S+)", message.body)
    assert match, message.body
    return match.group(1)


def sign_in(client, identifier, password=NEW_PASSWORD):
    return client.post(reverse("accounts:login"), {"username": identifier, "password": password})


class TestSignUpAndConfirmation:
    def test_unconfirmed_account_cannot_sign_in_and_is_told_why(self, client, mailoutbox):
        sign_up(client)
        response = sign_in(client, "nia")
        html = response.content.decode()
        assert response.status_code == 200
        assert "Confirm your email address before signing in" in html
        assert reverse("accounts:resend_verification") in html
        assert "_auth_user_id" not in client.session

    def test_confirmation_link_activates_sign_in(self, client, mailoutbox):
        sign_up(client)
        link = link_in(mailoutbox[0], "/accounts/confirm-email/")
        assert client.post(link).url == reverse("accounts:login")
        profile = Profile.objects.get(user__username="nia")
        assert profile.email_verified_at is not None
        assert AuditEvent.objects.filter(action=AuditAction.EMAIL_VERIFIED, actor_username="nia").exists()
        assert sign_in(client, "nia").status_code == 302

    def test_opening_the_link_does_not_confirm_until_the_button_is_pressed(self, client, mailoutbox):
        """Mail scanners open links automatically; only the POST counts."""
        sign_up(client)
        link = link_in(mailoutbox[0], "/accounts/confirm-email/")
        page = client.get(link)
        assert page.status_code == 200 and "Confirm email address" in page.content.decode()
        assert Profile.objects.get(user__username="nia").email_verified_at is None

    def test_link_works_once(self, client, mailoutbox):
        sign_up(client)
        link = link_in(mailoutbox[0], "/accounts/confirm-email/")
        client.post(link)
        again = client.post(link)
        assert again.status_code == 400 and "not valid" in again.content.decode()

    def test_expired_link_is_refused(self, client, mailoutbox, settings):
        sign_up(client)
        link = link_in(mailoutbox[0], "/accounts/confirm-email/")
        later = time.time() + (settings.CODEGUARD_EMAIL_VERIFICATION_HOURS + 1) * 3600
        with mock.patch("django.core.signing.time.time", return_value=later):
            assert client.post(link).status_code == 400
        assert Profile.objects.get(user__username="nia").email_verified_at is None

    def test_tampered_link_is_refused(self, client, mailoutbox):
        sign_up(client)
        link = link_in(mailoutbox[0], "/accounts/confirm-email/")
        assert client.post(link[:-3] + "abc/").status_code == 400

    def test_token_for_another_address_is_refused(self, analyst):
        token = tokens.make_token(analyst, "someone-else@example.com")
        assert tokens.read_token(token) is None

    def test_suspended_account_cannot_confirm(self, client, mailoutbox):
        sign_up(client)
        link = link_in(mailoutbox[0], "/accounts/confirm-email/")
        User.objects.filter(username="nia").update(is_active=False)
        assert client.post(link).status_code == 400

    def test_names_and_terms_are_required(self, client):
        response = sign_up(client, first_name="", accept_terms="")
        errors = response.context["form"].errors
        assert "first_name" in errors and "accept_terms" in errors
        assert not User.objects.filter(username="nia").exists()

    def test_honeypot_creates_nothing_but_looks_the_same(self, client, mailoutbox):
        response = sign_up(client, website="https://spam.example")
        assert response.status_code == 302 and response.url == reverse("accounts:check_email")
        assert not User.objects.filter(username="nia").exists()
        assert mailoutbox == []

    def test_sign_up_is_limited_per_network(self, client, mailoutbox):
        for i in range(5):
            sign_up(client, username=f"user{i}", email=f"user{i}@example.com")
        blocked = sign_up(client, username="user9", email="user9@example.com")
        assert blocked.status_code == 200 and "Too many sign-up attempts" in blocked.content.decode()
        assert not User.objects.filter(username="user9").exists()

    def test_resend_gives_the_same_answer_for_any_address(self, client, mailoutbox, analyst):
        sign_up(client)
        mailoutbox.clear()
        url = reverse("accounts:resend_verification")
        responses = [client.post(url, {"email": e}) for e in ("nia@example.com", "nobody@example.com", analyst.email)]
        assert {r.url for r in responses} == {reverse("accounts:check_email")}
        # Only accounts with an unconfirmed address get a message (alice was
        # created by an administrator and has not confirmed hers); unknown
        # addresses get nothing.
        assert sorted(m.to[0] for m in mailoutbox) == [analyst.email, "nia@example.com"]
        Profile.objects.filter(user=analyst).update(email_verified_at=timezone.now())
        mailoutbox.clear()
        client.post(url, {"email": analyst.email})
        assert mailoutbox == []

    def test_resend_is_limited_per_address(self, client, mailoutbox):
        sign_up(client)
        url = reverse("accounts:resend_verification")
        for _ in range(4):
            client.post(url, {"email": "nia@example.com"})
        assert len(mailoutbox) == 3  # the sign-up email plus two resends; the limit is three per hour


class TestSignInWithEmail:
    def test_email_and_username_both_work(self, client, analyst):
        assert sign_in(client, "ALICE@example.com", PASSWORD).status_code == 302
        client.post(reverse("accounts:logout"))
        assert sign_in(client, "alice", PASSWORD).status_code == 302

    def test_failures_by_email_count_against_the_account(self, client, analyst):
        for _ in range(3):
            sign_in(client, "alice@example.com", "wrong-password")
        for _ in range(2):
            sign_in(client, "alice", "wrong-password")
        response = sign_in(client, "alice@example.com", PASSWORD)
        assert "Too many failed sign-in attempts" in response.content.decode()

    def test_email_addresses_are_unique_ignoring_case(self, analyst):
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create_user("mallory", email="ALICE@example.com", password=PASSWORD)


class TestEmailChange:
    def change(self, client, email="new@example.com"):
        return client.post(reverse("settings:account"), {"email": email, "current_password": PASSWORD})

    def test_new_address_must_be_confirmed_and_old_address_is_told(self, analyst_client, analyst, mailoutbox):
        self.change(analyst_client)
        assert sorted(m.to[0] for m in mailoutbox) == ["alice@example.com", "new@example.com"]
        notice = next(m for m in mailoutbox if m.to == ["alice@example.com"])
        assert "n***@example.com" in notice.body and "/confirm-email/" not in notice.body
        confirm = next(m for m in mailoutbox if m.to == ["new@example.com"])
        analyst_client.post(link_in(confirm, "/accounts/confirm-email/"))
        analyst.refresh_from_db()
        assert analyst.email == "new@example.com"
        assert analyst.profile.pending_email == "" and analyst.profile.email_verified_at is not None
        assert AuditEvent.objects.filter(action=AuditAction.EMAIL_CHANGE, actor=analyst).exists()

    def test_cancelled_change_link_stops_working(self, analyst_client, analyst, mailoutbox):
        self.change(analyst_client)
        link = link_in(next(m for m in mailoutbox if m.to == ["new@example.com"]), "/accounts/confirm-email/")
        analyst_client.post(reverse("settings:cancel_email_change"))
        assert analyst_client.post(link).status_code == 400
        analyst.refresh_from_db()
        assert analyst.email == "alice@example.com"

    def test_address_taken_meanwhile_is_not_applied(self, analyst_client, analyst, mailoutbox):
        self.change(analyst_client)
        link = link_in(next(m for m in mailoutbox if m.to == ["new@example.com"]), "/accounts/confirm-email/")
        User.objects.create_user("eve", email="new@example.com", password=PASSWORD)
        analyst_client.post(link)
        analyst.refresh_from_db()
        assert analyst.email == "alice@example.com"

    def test_failed_delivery_leaves_the_address_unchanged(self, analyst_client, analyst):
        with mock.patch("accounts.emails.EmailMessage.send", side_effect=OSError("down")):
            response = self.change(analyst_client)
        assert response.status_code == 302
        analyst.refresh_from_db()
        assert analyst.profile.pending_email == ""

    def test_existing_account_can_confirm_its_address(self, analyst_client, analyst, mailoutbox):
        analyst_client.post(reverse("settings:send_verification"))
        analyst_client.post(link_in(mailoutbox[0], "/accounts/confirm-email/"))
        analyst.profile.refresh_from_db()
        assert analyst.profile.email_verified


class TestPasswords:
    def test_reset_confirms_the_address_and_sends_a_notice(self, client, mailoutbox):
        sign_up(client)
        mailoutbox.clear()
        client.post(reverse("accounts:password_reset"), {"email": "nia@example.com"})
        link = link_in(mailoutbox[0], "/accounts/reset/")
        form_url = client.get(link).url  # Django moves the token into the session
        response = client.post(
            form_url, {"new_password1": "Brand-new-passphrase-7", "new_password2": "Brand-new-passphrase-7"}
        )
        assert response.status_code == 302
        user = User.objects.get(username="nia")
        assert user.profile.email_verified_at is not None
        assert AuditEvent.objects.filter(action=AuditAction.PASSWORD_RESET, actor=user).exists()
        assert "password of your CodeGuard account" in mailoutbox[-1].body
        assert sign_in(client, "nia", "Brand-new-passphrase-7").status_code == 302

    def test_reset_requests_are_limited_per_address(self, client, analyst, mailoutbox):
        for _ in range(5):
            response = client.post(reverse("accounts:password_reset"), {"email": analyst.email})
            assert response.url == reverse("accounts:password_reset_done")
        assert len(mailoutbox) == 3
        events = AuditEvent.objects.filter(action=AuditAction.PASSWORD_RESET_REQUEST)
        assert events.count() == 3 and "@" not in str(events.first().metadata)

    def test_reset_links_expire_after_an_hour(self, settings):
        assert settings.PASSWORD_RESET_TIMEOUT == 3600

    def test_password_change_sends_a_notice(self, analyst_client, mailoutbox):
        analyst_client.post(
            reverse("accounts:password_change"),
            {
                "old_password": PASSWORD,
                "new_password1": "An0ther-long-passphrase",
                "new_password2": "An0ther-long-passphrase",
            },
        )
        assert mailoutbox and mailoutbox[0].to == ["alice@example.com"]
        assert "was changed" in mailoutbox[0].body


class TestInvitations:
    def invite(self, client, email="dev@example.com", role="analyst"):
        return client.post(reverse("settings:invite"), {"email": email, "role": role})

    def test_admin_invites_and_the_invitee_creates_the_account(self, admin_client, mailoutbox):
        self.invite(admin_client, role="viewer")
        invitation = Invitation.objects.get()
        assert invitation.sent_at is not None and len(invitation.token_hash) == 64
        link = link_in(mailoutbox[0], "/accounts/invitation/")
        assert link.rstrip("/").rsplit("/", 1)[-1] not in invitation.token_hash  # only the hash is stored

        guest = Client()
        page = guest.get(link)
        assert page.status_code == 200 and "dev@example.com" in page.content.decode()
        response = guest.post(
            link,
            {
                "first_name": "Dev",
                "username": "dev",
                "password1": NEW_PASSWORD,
                "password2": NEW_PASSWORD,
                "accept_terms": "on",
            },
        )
        assert response.status_code == 302
        user = User.objects.get(username="dev")
        assert user.email == "dev@example.com"
        assert user.profile.role == Role.VIEWER
        assert user.profile.origin == AccountOrigin.INVITATION and user.profile.email_verified
        assert guest.get(reverse("core:dashboard")).status_code == 200
        invitation.refresh_from_db()
        assert invitation.accepted_user == user
        assert Client().get(link).status_code == 400  # single use

    def test_shown_link_survives_failed_email(self, admin_client):
        with mock.patch("accounts.emails.EmailMessage.send", side_effect=OSError("down")):
            self.invite(admin_client)
        page = admin_client.get(reverse("settings:users")).content.decode()
        assert "/accounts/invitation/" in page and "was not emailed" in page
        assert Invitation.objects.get().sent_at is None
        # Shown once only.
        assert "/accounts/invitation/" not in admin_client.get(reverse("settings:users")).content.decode()

    def test_resend_replaces_the_link_and_revoke_kills_it(self, admin_client, mailoutbox):
        self.invite(admin_client)
        first = link_in(mailoutbox[0], "/accounts/invitation/")
        invitation = Invitation.objects.get()
        admin_client.post(reverse("settings:resend_invitation", args=[invitation.pk]))
        second = link_in(mailoutbox[1], "/accounts/invitation/")
        assert Client().get(first).status_code == 400 and Client().get(second).status_code == 200
        admin_client.post(reverse("settings:revoke_invitation", args=[invitation.pk]))
        assert Client().get(second).status_code == 400

    def test_expired_invitation_is_refused(self, admin_client, mailoutbox):
        self.invite(admin_client)
        Invitation.objects.update(expires_at=timezone.now() - timedelta(minutes=1))
        assert Client().get(link_in(mailoutbox[0], "/accounts/invitation/")).status_code == 400

    def test_existing_address_cannot_be_invited(self, admin_client, analyst):
        self.invite(admin_client, email="ALICE@example.com")
        assert not Invitation.objects.exists()

    def test_reinviting_reuses_the_open_invitation(self, admin_client, mailoutbox):
        self.invite(admin_client)
        self.invite(admin_client, email="DEV@example.com", role="admin")
        invitation = Invitation.objects.get()
        assert invitation.role == Role.ADMIN

    def test_address_taken_before_acceptance(self, admin_client, mailoutbox):
        self.invite(admin_client)
        User.objects.create_user("squatter", email="dev@example.com", password=PASSWORD)
        response = Client().post(
            link_in(mailoutbox[0], "/accounts/invitation/"),
            {
                "first_name": "Dev",
                "username": "dev",
                "password1": NEW_PASSWORD,
                "password2": NEW_PASSWORD,
                "accept_terms": "on",
            },
        )
        assert "already exists" in response.content.decode()
        assert not User.objects.filter(username="dev").exists()

    def test_only_administrators_can_invite(self, analyst_client, viewer_client):
        for client in (analyst_client, viewer_client):
            assert self.invite(client).status_code == 403
        assert not Invitation.objects.exists()


class TestUserManagement:
    def test_suspension_ends_sessions_and_blocks_sign_in(self, admin_client, analyst):
        victim = Client()
        victim.force_login(analyst)
        victim.get(reverse("core:dashboard"))
        admin_client.post(reverse("settings:suspend_user", args=[analyst.pk]))
        analyst.refresh_from_db()
        assert not analyst.is_active
        assert victim.get(reverse("core:dashboard")).status_code == 302
        assert sign_in(Client(), "alice", PASSWORD).status_code == 200
        assert AuditEvent.objects.filter(action=AuditAction.USER_SUSPEND).exists()
        admin_client.post(reverse("settings:reactivate_user", args=[analyst.pk]))
        assert sign_in(Client(), "alice", PASSWORD).status_code == 302

    def test_cannot_suspend_self_or_superusers(self, admin_client, admin_user):
        root = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        for target in (admin_user, root):
            admin_client.post(reverse("settings:suspend_user", args=[target.pk]))
            target.refresh_from_db()
            assert target.is_active

    def test_non_admins_cannot_manage_users(self, analyst_client, other_analyst):
        for name in ("suspend_user", "reactivate_user", "send_password_reset"):
            assert analyst_client.post(reverse(f"settings:{name}", args=[other_analyst.pk])).status_code == 403
        assert analyst_client.get(reverse("settings:user_detail", args=[other_analyst.pk])).status_code == 403

    def test_admin_can_send_a_reset_link_without_seeing_a_password(self, admin_client, analyst, mailoutbox):
        admin_client.post(reverse("settings:send_password_reset", args=[analyst.pk]))
        assert mailoutbox[0].to == [analyst.email] and "/accounts/reset/" in mailoutbox[0].body

    def test_search_and_filters(self, admin_client, analyst, viewer):
        User.objects.filter(pk=viewer.pk).update(is_active=False)
        page = admin_client.get(reverse("settings:users"), {"q": "ALI"})
        assert [u.username for u in page.context["page_obj"]] == ["alice"]
        suspended = admin_client.get(reverse("settings:users"), {"status": "suspended"})
        assert [u.username for u in suspended.context["page_obj"]] == ["victor"]
        admins = admin_client.get(reverse("settings:users"), {"role": "admin"})
        assert [u.username for u in admins.context["page_obj"]] == ["ada"]

    def test_detail_page_shows_activity(self, admin_client, analyst):
        admin_client.post(reverse("settings:change_role", args=[analyst.pk]), {"role": "viewer", "next": "detail"})
        page = admin_client.get(reverse("settings:user_detail", args=[analyst.pk]))
        assert page.status_code == 200 and "Changed user role" in page.content.decode()

    def test_suspended_users_session_epoch_moves(self, admin_client, analyst):
        before = preferences_for(analyst).session_epoch
        admin_client.post(reverse("settings:suspend_user", args=[analyst.pk]))
        assert preferences_for(User.objects.get(pk=analyst.pk)).session_epoch == before + 1


def test_console_email_is_not_reported_as_sent(admin_client, settings):
    """On a deployment without real email the admin must be told to pass the link on."""
    settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    admin_client.post(reverse("settings:invite"), {"email": "dev@example.com", "role": "analyst"})
    assert Invitation.objects.get().sent_at is None
    assert "was not emailed" in admin_client.get(reverse("settings:users")).content.decode()
