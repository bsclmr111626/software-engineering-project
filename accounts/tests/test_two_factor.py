"""Two-step sign-in (accounts/two_factor.py): the code maths, turning it on and
off, the extra sign-in step, backup codes, limits and administrator resets."""

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts import two_factor
from accounts.models import BackupCode, Profile, Role, TwoFactorDevice, Workspace
from accounts.preferences import preferences_for
from audit.models import AuditAction, AuditEvent
from conftest import PASSWORD

pytestmark = pytest.mark.django_db
User = get_user_model()
LOGIN = reverse("accounts:login")
CODE_STEP = reverse("accounts:two_factor")


def current_code(user, offset=0):
    return two_factor.code_at(user.two_factor.secret, two_factor.current_step() + offset)


def turn_on(user):
    secret = two_factor.new_secret()
    # A step in the past, so the current code is still unused.
    _, codes = two_factor.enable(user, secret, two_factor.current_step() - 5)
    user.refresh_from_db()
    return codes


def sign_in(client, username="alice", password=PASSWORD, **extra):
    return client.post(LOGIN, {"username": username, "password": password, **extra})


class TestCodes:
    # RFC 6238, appendix B (SHA-1), truncated to six digits.
    SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"

    @pytest.mark.parametrize(
        ("unix_time", "expected"),
        [(59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037")],
    )
    def test_rfc_6238_vectors(self, unix_time, expected):
        assert two_factor.code_at(self.SECRET, two_factor.current_step(unix_time)) == expected

    def test_one_step_of_clock_drift_is_accepted_but_not_two(self):
        now = 1111111109
        step = two_factor.current_step(now)
        assert two_factor.matching_step(self.SECRET, two_factor.code_at(self.SECRET, step - 1), now=now) == step - 1
        assert two_factor.matching_step(self.SECRET, two_factor.code_at(self.SECRET, step + 1), now=now) == step + 1
        assert two_factor.matching_step(self.SECRET, two_factor.code_at(self.SECRET, step - 2), now=now) is None

    def test_spaces_are_ignored_and_junk_is_refused(self):
        code = two_factor.code_at(self.SECRET, two_factor.current_step(59))
        assert two_factor.matching_step(self.SECRET, f"{code[:3]} {code[3:]}", now=59) is not None
        for junk in ("", "12345", "1234567", "abcdef", None):
            assert two_factor.matching_step(self.SECRET, junk, now=59) is None

    def test_new_secrets_are_random_160_bit_keys(self):
        a, b = two_factor.new_secret(), two_factor.new_secret()
        assert a != b and len(a) == 32
        assert len(two_factor._key(a)) == 20

    def test_provisioning_uri_names_the_issuer_and_account(self, analyst):
        uri = two_factor.provisioning_uri(analyst, "ABCD")
        assert uri.startswith("otpauth://totp/CodeGuard%3Aalice?")
        assert "secret=ABCD" in uri and "issuer=CodeGuard" in uri

    def test_qr_code_uses_tokens_not_colours(self):
        svg = str(two_factor.qr_svg("otpauth://totp/x?secret=ABCD"))
        assert svg.startswith("<svg") and 'class="cg-qr-dark"' in svg
        assert "#" not in svg and "fill=" not in svg


class TestSetup:
    def test_setup_page_shows_a_qr_code_and_key_without_saving_anything(self, analyst_client, analyst):
        response = analyst_client.get(reverse("settings:two_factor_setup"))
        assert response.status_code == 200
        assert b"cg-qr-dark" in response.content
        secret = analyst_client.session[two_factor.SETUP_KEY]
        assert two_factor.grouped(secret).encode() in response.content
        assert not TwoFactorDevice.objects.exists()
        # The key stays the same on reload, so a slow scan still works.
        analyst_client.get(reverse("settings:two_factor_setup"))
        assert analyst_client.session[two_factor.SETUP_KEY] == secret

    def test_right_code_and_password_turn_it_on_and_show_backup_codes_once(self, analyst_client, analyst):
        analyst_client.get(reverse("settings:two_factor_setup"))
        secret = analyst_client.session[two_factor.SETUP_KEY]
        epoch = preferences_for(analyst).session_epoch
        code = two_factor.code_at(secret, two_factor.current_step())
        response = analyst_client.post(
            reverse("settings:two_factor_setup"), {"code": code, "current_password": PASSWORD}
        )
        assert response.status_code == 302 and response.url == reverse("settings:backup_codes")
        device = TwoFactorDevice.objects.get(user=analyst)
        assert device.secret == secret
        assert BackupCode.objects.filter(user=analyst, used_at__isnull=True).count() == 10
        assert AuditEvent.objects.filter(actor=analyst, action=AuditAction.TWO_FACTOR_ENABLE).exists()
        analyst.refresh_from_db()
        analyst._cg_preferences = None
        assert preferences_for(analyst).session_epoch == epoch + 1  # other sessions signed out
        assert two_factor.SETUP_KEY not in analyst_client.session

        page = analyst_client.get(reverse("settings:backup_codes"))
        codes = analyst_client.session[two_factor.CODES_KEY]
        assert len(codes) == 10 and all(c.encode() in page.content for c in codes)
        # Only hashes are stored.
        assert not BackupCode.objects.filter(code_hash__in=codes).exists()
        download = analyst_client.get(reverse("settings:backup_codes_download"))
        assert download["Content-Disposition"].startswith("attachment") and codes[0] in download.content.decode()
        assert download["Cache-Control"] == "no-store"
        analyst_client.post(reverse("settings:backup_codes"))
        assert analyst_client.get(reverse("settings:backup_codes")).url == reverse("settings:security")

    def test_the_code_used_to_confirm_cannot_sign_in_again(self, analyst_client, analyst):
        analyst_client.get(reverse("settings:two_factor_setup"))
        secret = analyst_client.session[two_factor.SETUP_KEY]
        code = two_factor.code_at(secret, two_factor.current_step())
        analyst_client.post(reverse("settings:two_factor_setup"), {"code": code, "current_password": PASSWORD})
        assert two_factor.verify(analyst, code) is None

    @pytest.mark.parametrize(("code", "password"), [("000000", PASSWORD), (None, "wrong-password")])
    def test_wrong_code_or_password_changes_nothing(self, analyst_client, analyst, code, password):
        analyst_client.get(reverse("settings:two_factor_setup"))
        secret = analyst_client.session[two_factor.SETUP_KEY]
        if code is None:
            code = two_factor.code_at(secret, two_factor.current_step())
        elif code == two_factor.code_at(secret, two_factor.current_step()):
            code = "111111"
        response = analyst_client.post(
            reverse("settings:two_factor_setup"), {"code": code, "current_password": password}
        )
        assert response.status_code == 200 and not TwoFactorDevice.objects.exists()

    def test_security_page_shows_the_state(self, analyst_client, analyst):
        assert b"Set up" in analyst_client.get(reverse("settings:security")).content
        turn_on(analyst)
        page = analyst_client.get(reverse("settings:security")).content.decode()
        assert "On since" in page and "10 backup codes left" in page

    def test_data_export_says_whether_it_is_on_but_never_the_key(self, analyst_client, analyst):
        turn_on(analyst)
        export = analyst_client.get(reverse("settings:export_data")).json()
        assert export["account"]["two_step_sign_in"] is True
        assert analyst.two_factor.secret not in str(export)


class TestSignIn:
    def test_password_alone_does_not_sign_in(self, client, analyst):
        turn_on(analyst)
        response = sign_in(client)
        assert response.status_code == 302 and response.url == CODE_STEP
        assert "_auth_user_id" not in client.session
        assert client.get(reverse("core:dashboard")).status_code == 302

    def test_right_code_signs_in_and_goes_to_next(self, client, analyst):
        turn_on(analyst)
        sign_in(client, next="/reports/")
        response = client.post(CODE_STEP, {"code": current_code(analyst)})
        assert response.status_code == 302 and response.url == "/reports/"
        assert client.session["_auth_user_id"] == str(analyst.pk)
        assert AuditEvent.objects.filter(actor=analyst, action=AuditAction.LOGIN).exists()

    def test_a_code_works_only_once(self, client, analyst):
        turn_on(analyst)
        code = current_code(analyst)
        sign_in(client)
        client.post(CODE_STEP, {"code": code})
        other = Client()
        sign_in(other)
        response = other.post(CODE_STEP, {"code": code})
        assert response.status_code == 200 and "_auth_user_id" not in other.session
        assert AuditEvent.objects.filter(actor=analyst, action=AuditAction.TWO_FACTOR_FAILED).count() == 1

    def test_offsite_next_is_ignored(self, client, analyst):
        turn_on(analyst)
        sign_in(client, next="https://evil.example/")
        response = client.post(CODE_STEP, {"code": current_code(analyst)})
        assert response.url == reverse("core:start")

    def test_backup_code_signs_in_once(self, client, analyst):
        codes = turn_on(analyst)
        sign_in(client)
        response = client.post(CODE_STEP, {"code": codes[0].lower().replace("-", " ")})
        assert response.status_code == 302 and client.session["_auth_user_id"] == str(analyst.pk)
        assert two_factor.backup_codes_left(analyst) == 9
        event = AuditEvent.objects.get(actor=analyst, action=AuditAction.BACKUP_CODE_USED)
        assert event.metadata["codes_left"] == 9
        again = Client()
        sign_in(again)
        assert again.post(CODE_STEP, {"code": codes[0]}).status_code == 200
        assert "_auth_user_id" not in again.session

    def test_new_backup_codes_replace_the_old(self, analyst_client, analyst):
        old = turn_on(analyst)
        response = analyst_client.post(reverse("settings:two_factor_codes"), {"current_password": PASSWORD})
        assert response.url == reverse("settings:backup_codes")
        new = analyst_client.session[two_factor.CODES_KEY]
        assert set(new).isdisjoint(old) and BackupCode.objects.filter(user=analyst).count() == 10
        assert two_factor.verify(analyst, old[0]) is None
        assert two_factor.verify(analyst, new[0]) == "backup"

    def test_too_many_wrong_codes_end_the_attempt(self, client, analyst, settings):
        settings.CODEGUARD_LOGIN_MAX_FAILURES = 3
        turn_on(analyst)
        sign_in(client)
        for _ in range(3):
            assert client.post(CODE_STEP, {"code": "000000"}).status_code == 200
        response = client.post(CODE_STEP, {"code": current_code(analyst)})
        assert response.url == LOGIN and "_auth_user_id" not in client.session
        assert AuditEvent.objects.filter(action=AuditAction.LOGIN_THROTTLED, actor=analyst).exists()
        # Starting over does not reset the count.
        sign_in(client)
        assert client.post(CODE_STEP, {"code": current_code(analyst)}).url == LOGIN

    def test_the_code_step_expires(self, client, analyst):
        turn_on(analyst)
        sign_in(client)
        session = client.session
        data = session[two_factor.PENDING_KEY]
        data["started"] = (timezone.now() - timedelta(minutes=two_factor.PENDING_MINUTES + 1)).isoformat()
        session[two_factor.PENDING_KEY] = data
        session.save()
        assert client.post(CODE_STEP, {"code": current_code(analyst)}).url == LOGIN
        assert "_auth_user_id" not in client.session

    def test_code_step_without_a_password_goes_back_to_sign_in(self, client, analyst):
        turn_on(analyst)
        assert client.get(CODE_STEP).url == LOGIN
        assert client.post(CODE_STEP, {"code": current_code(analyst)}).url == LOGIN

    def test_password_change_voids_a_pending_step(self, client, analyst):
        turn_on(analyst)
        sign_in(client)
        analyst.set_password("A-different-long-passphrase-9")
        analyst.save()
        assert client.post(CODE_STEP, {"code": current_code(analyst)}).url == LOGIN

    def test_suspended_account_cannot_finish(self, client, analyst):
        turn_on(analyst)
        sign_in(client)
        User.objects.filter(pk=analyst.pk).update(is_active=False)
        assert client.post(CODE_STEP, {"code": current_code(analyst)}).url == LOGIN

    def test_accounts_without_it_sign_in_as_before(self, client, analyst):
        response = sign_in(client)
        assert response.status_code == 302 and client.session["_auth_user_id"] == str(analyst.pk)

    def test_admin_sign_in_page_cannot_skip_the_code(self, client, admin_user):
        admin_user.is_staff = True
        admin_user.save()
        turn_on(admin_user)
        response = client.get("/admin/login/?next=/admin/")
        assert response.status_code == 302 and response.url.startswith(LOGIN + "?next=")
        client.post("/admin/login/", {"username": "ada", "password": PASSWORD})
        assert "_auth_user_id" not in client.session

    def test_turning_it_off_needs_the_password(self, analyst_client, analyst):
        turn_on(analyst)
        analyst_client.post(reverse("settings:two_factor_disable"), {"current_password": "nope"})
        assert TwoFactorDevice.objects.filter(user=analyst).exists()
        analyst_client.post(reverse("settings:two_factor_disable"), {"current_password": PASSWORD})
        assert not TwoFactorDevice.objects.filter(user=analyst).exists()
        assert not BackupCode.objects.filter(user=analyst).exists()
        assert AuditEvent.objects.filter(actor=analyst, action=AuditAction.TWO_FACTOR_DISABLE).exists()


class TestRecovery:
    def test_workspace_admin_can_reset_a_member(self, admin_client, admin_user, analyst):
        turn_on(analyst)
        detail = admin_client.get(reverse("settings:user_detail", args=[analyst.pk])).content.decode()
        assert "Reset two-step sign-in" in detail
        assert "2-step" in admin_client.get(reverse("settings:users")).content.decode()
        admin_client.post(reverse("settings:reset_two_factor", args=[analyst.pk]))
        assert not two_factor.enabled(analyst)
        event = AuditEvent.objects.get(action=AuditAction.TWO_FACTOR_RESET)
        assert event.actor == admin_user and event.object_id == str(analyst.pk)

    def test_admin_cannot_reset_someone_in_another_workspace(self, admin_client):
        other_space = Workspace.objects.create(name="Borealis")
        outsider = User.objects.create_user("bea", "bea@example.com", PASSWORD)
        Profile.objects.filter(user=outsider).update(workspace=other_space, role=Role.ANALYST)
        turn_on(outsider)
        response = admin_client.post(reverse("settings:reset_two_factor", args=[outsider.pk]))
        assert response.status_code == 404 and two_factor.enabled(outsider)

    def test_analysts_cannot_reset_anyone(self, analyst_client, other_analyst):
        turn_on(other_analyst)
        response = analyst_client.post(reverse("settings:reset_two_factor", args=[other_analyst.pk]))
        assert response.status_code in (302, 403) and two_factor.enabled(other_analyst)

    def test_admin_cannot_reset_their_own(self, admin_client, admin_user):
        turn_on(admin_user)
        admin_client.post(reverse("settings:reset_two_factor", args=[admin_user.pk]))
        assert two_factor.enabled(admin_user)

    def test_operator_command(self, analyst):
        turn_on(analyst)
        out = StringIO()
        call_command("reset_two_factor", "alice", stdout=out)
        assert not two_factor.enabled(analyst) and "is off" in out.getvalue()
        assert AuditEvent.objects.filter(action=AuditAction.TWO_FACTOR_RESET, object_id=str(analyst.pk)).exists()

    def test_deleting_an_account_removes_its_device_and_codes(self, analyst):
        turn_on(analyst)
        analyst.delete()
        assert not TwoFactorDevice.objects.exists() and not BackupCode.objects.exists()
