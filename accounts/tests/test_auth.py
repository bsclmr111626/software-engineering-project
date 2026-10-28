from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, Role
from accounts.permissions import get_role
from audit.models import AuditAction, AuditEvent
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
User = get_user_model()


def register(client, **extra):
    data = {
        "username": "newuser",
        "email": "new@example.com",
        "password1": "A-very-long-passphrase-42",
        "password2": "A-very-long-passphrase-42",
    }
    data.update(extra)
    return client.post(reverse("accounts:register"), data)


class TestRegistration:
    def test_registration_creates_user_with_default_role_and_logs_in(self, client):
        response = register(client)
        assert response.status_code == 302
        user = User.objects.get(username="newuser")
        assert get_role(user) == Role.ANALYST
        assert client.get(reverse("core:dashboard")).status_code == 200
        assert AuditEvent.objects.filter(action=AuditAction.REGISTER, actor=user).exists()

    def test_role_cannot_be_chosen_during_registration(self, client):
        register(client, role="admin", is_superuser="on", is_staff="on")
        user = User.objects.get(username="newuser")
        assert get_role(user) == Role.ANALYST
        assert not user.is_superuser and not user.is_staff

    def test_weak_password_is_rejected(self, client):
        response = register(client, password1="password", password2="password")
        assert response.status_code == 200
        assert "password2" in response.context["form"].errors
        assert not User.objects.filter(username="newuser").exists()

    def test_duplicate_email_is_rejected(self, client, analyst):
        response = register(client, email=analyst.email.upper())
        assert "email" in response.context["form"].errors

    def test_password_is_hashed(self, client):
        register(client)
        user = User.objects.get(username="newuser")
        assert user.password != "A-very-long-passphrase-42"
        assert user.check_password("A-very-long-passphrase-42")


class TestLoginLogout:
    def test_successful_login(self, client, analyst):
        response = client.post(reverse("accounts:login"), {"username": "alice", "password": PASSWORD})
        assert response.status_code == 302
        assert response.url == reverse("core:start")
        assert AuditEvent.objects.filter(action=AuditAction.LOGIN, actor=analyst).exists()

    def test_invalid_credentials(self, client, analyst):
        response = client.post(reverse("accounts:login"), {"username": "alice", "password": "wrong-password"})
        assert response.status_code == 200
        assert response.context["form"].errors
        event = AuditEvent.objects.get(action=AuditAction.LOGIN_FAILED)
        assert event.metadata == {"attempted_username": "alice"}
        assert "wrong-password" not in str(event.metadata)

    def test_open_redirect_is_ignored(self, client, analyst):
        response = client.post(
            reverse("accounts:login") + "?next=https://evil.example.com/",
            {"username": "alice", "password": PASSWORD, "next": "https://evil.example.com/"},
        )
        assert response.status_code == 302
        assert "evil.example.com" not in response.url

    def test_logout_requires_post_and_ends_session(self, analyst_client, analyst):
        assert analyst_client.get(reverse("accounts:logout")).status_code == 405
        response = analyst_client.post(reverse("accounts:logout"))
        assert response.status_code == 302
        assert analyst_client.get(reverse("core:dashboard")).status_code == 302
        assert AuditEvent.objects.filter(action=AuditAction.LOGOUT, actor=analyst).exists()

    def test_protected_pages_require_login(self, client):
        for name in (
            "core:dashboard",
            "threats:list",
            "reports:list",
            "audit:log",
            "core:supply_chain",
            "core:risk",
            "settings:profile",
            "threats:controls",
        ):
            response = client.get(reverse(name))
            assert response.status_code == 302, name
            assert response.url.startswith(reverse("accounts:login"))

    def test_login_form_enforces_csrf(self, analyst):
        strict = Client(enforce_csrf_checks=True)
        response = strict.post(reverse("accounts:login"), {"username": "alice", "password": PASSWORD})
        assert response.status_code == 403

    def test_password_change_is_audited(self, analyst_client, analyst):
        response = analyst_client.post(
            reverse("accounts:password_change"),
            {
                "old_password": PASSWORD,
                "new_password1": "An0ther-long-passphrase",
                "new_password2": "An0ther-long-passphrase",
            },
        )
        assert response.status_code == 302
        assert AuditEvent.objects.filter(action=AuditAction.PASSWORD_CHANGE).exists()

    def test_password_reset_sends_email_without_disclosing_accounts(self, client, analyst, mailoutbox):
        known = client.post(reverse("accounts:password_reset"), {"email": analyst.email})
        unknown = client.post(reverse("accounts:password_reset"), {"email": "nobody@example.com"})
        assert known.status_code == unknown.status_code == 302
        assert known.url == unknown.url
        assert len(mailoutbox) == 1
        assert "/accounts/reset/" in mailoutbox[0].body


class TestRoles:
    def test_new_users_get_profile_automatically(self, db):
        user = User.objects.create_user("plain", password=PASSWORD)
        assert Profile.objects.get(user=user).role == Role.ANALYST

    def test_superuser_is_admin(self, db):
        root = User.objects.create_superuser("root", "root@example.com", PASSWORD)
        assert get_role(root) == Role.ADMIN

    def test_admin_can_change_role(self, admin_client, analyst, admin_user):
        response = admin_client.post(reverse("accounts:change_role", args=[analyst.pk]), {"role": "viewer"})
        assert response.status_code == 302
        analyst.profile.refresh_from_db()
        assert analyst.profile.role == Role.VIEWER
        event = AuditEvent.objects.get(action=AuditAction.ROLE_CHANGE)
        assert event.metadata == {"old_role": "analyst", "new_role": "viewer"}

    def test_admin_cannot_change_own_role(self, admin_client, admin_user):
        admin_client.post(reverse("accounts:change_role", args=[admin_user.pk]), {"role": "viewer"})
        admin_user.profile.refresh_from_db()
        assert admin_user.profile.role == Role.ADMIN

    def test_invalid_role_rejected(self, admin_client, analyst):
        admin_client.post(reverse("accounts:change_role", args=[analyst.pk]), {"role": "superadmin"})
        analyst.profile.refresh_from_db()
        assert analyst.profile.role == Role.ANALYST

    def test_analyst_cannot_change_roles(self, analyst_client, analyst, viewer):
        assert analyst_client.get(reverse("settings:users")).status_code == 403
        assert analyst_client.get(reverse("settings:organization")).status_code == 403
        response = analyst_client.post(reverse("accounts:change_role", args=[analyst.pk]), {"role": "admin"})
        assert response.status_code == 403
        analyst.profile.refresh_from_db()
        assert analyst.profile.role == Role.ANALYST

    def test_viewer_cannot_change_roles(self, viewer_client, viewer):
        response = viewer_client.post(reverse("accounts:change_role", args=[viewer.pk]), {"role": "admin"})
        assert response.status_code == 403

    def test_admin_user_list(self, admin_client, analyst):
        response = admin_client.get(reverse("settings:users"))
        assert response.status_code == 200
        assert b"alice" in response.content


class TestLoginThrottling:
    """Sign-in limits (accounts/throttling.py). Defaults: 5 per username, 20 per IP, 15 minutes."""

    def fail(self, client, username="alice", ip="10.0.0.1"):
        return client.post(
            reverse("accounts:login"), {"username": username, "password": "wrong-password"}, REMOTE_ADDR=ip
        )

    def login(self, client, username="alice", ip="10.0.0.1"):
        return client.post(reverse("accounts:login"), {"username": username, "password": PASSWORD}, REMOTE_ADDR=ip)

    def test_correct_password_is_refused_after_too_many_failures(self, client, analyst):
        for _ in range(5):
            self.fail(client)
        response = self.login(client)
        assert response.status_code == 200
        assert "Too many failed sign-in attempts" in response.content.decode()
        assert "_auth_user_id" not in client.session
        assert AuditEvent.objects.filter(
            action=AuditAction.LOGIN_THROTTLED, metadata__attempted_username="alice"
        ).exists()
        # A refused attempt never reaches the password check, so it does not extend the lock.
        assert AuditEvent.objects.filter(action=AuditAction.LOGIN_FAILED).count() == 5

    def test_lock_is_per_username_and_case_insensitive(self, client, analyst, other_analyst):
        for _ in range(5):
            self.fail(client, username="ALICE")
        assert "Too many" in self.login(client, username="alice").content.decode()
        assert self.login(client, username=other_analyst.username).status_code == 302

    def test_four_failures_do_not_lock(self, client, analyst):
        for _ in range(4):
            self.fail(client)
        assert self.login(client).status_code == 302

    def test_successful_sign_in_resets_the_username_count(self, client, analyst):
        for _ in range(4):
            self.fail(client)
        assert self.login(client).status_code == 302
        client.post(reverse("accounts:logout"))
        for _ in range(4):
            self.fail(client)
        assert self.login(client).status_code == 302

    def test_lock_expires_after_the_window(self, client, analyst):
        for _ in range(5):
            self.fail(client)
        later = timezone.now() + timedelta(minutes=16)
        with mock.patch("accounts.throttling.timezone.now", return_value=later):
            assert self.login(client).status_code == 302

    def test_ip_limit_stops_username_spraying(self, client, analyst):
        for i in range(20):
            self.fail(client, username=f"user{i}", ip="10.9.9.9")
        assert "Too many" in self.login(client, ip="10.9.9.9").content.decode()
        assert self.login(client, ip="10.0.0.2").status_code == 302


class TestRegistrationPolicy:
    def test_closed_registration_refuses_and_hides_links(self, client, settings):
        settings.CODEGUARD_REGISTRATION = "closed"
        response = register(client)
        assert response.status_code == 403
        assert not User.objects.filter(username="newuser").exists()
        for name in ("core:landing", "accounts:login"):
            assert reverse("accounts:register") not in client.get(reverse(name)).content.decode()

    def test_domain_registration_accepts_only_listed_domains(self, client, settings):
        settings.CODEGUARD_REGISTRATION = "domain"
        settings.CODEGUARD_REGISTRATION_DOMAINS = ["example.edu"]
        response = register(client, email="someone@gmail.com")
        assert response.status_code == 200
        assert "organization's email domains" in response.context["form"].errors["email"][0]
        assert register(client, email="Student@EXAMPLE.edu").status_code == 302
        assert User.objects.get(username="newuser").email == "student@example.edu"

    def test_open_registration_is_flagged_by_the_deploy_check(self, settings):
        from accounts.checks import open_registration

        settings.DEBUG = False
        settings.CODEGUARD_REGISTRATION = "open"
        assert [w.id for w in open_registration(None)] == ["codeguard.W001"]
        settings.CODEGUARD_REGISTRATION = "closed"
        assert open_registration(None) == []
