"""Email delivery (Brevo backend, test command, deploy check) and the
privacy, terms and contact pages."""

import io
import json
import urllib.error
from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage, get_connection
from django.core.management import CommandError, call_command
from django.urls import reverse

from core.email import EmailDeliveryError, delivers_email, describe_backend

pytestmark = pytest.mark.django_db

BREVO = "core.email.BrevoEmailBackend"


class FakeResponse:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def brevo(settings, **kwargs):
    settings.EMAIL_BACKEND = BREVO
    settings.BREVO_API_KEY = "test-key"
    settings.DEFAULT_FROM_EMAIL = "CodeGuard <noreply@example.com>"
    return get_connection(BREVO, **kwargs)


class TestBrevoBackend:
    def test_posts_the_message_to_the_api(self, settings):
        connection = brevo(settings)
        with mock.patch("core.email.urllib.request.urlopen", return_value=FakeResponse()) as urlopen:
            sent = EmailMessage("Subject", "Body text", to=["a@example.com"], connection=connection).send()
        assert sent == 1
        request = urlopen.call_args.args[0]
        assert request.full_url == "https://api.brevo.com/v3/smtp/email"
        assert request.get_header("Api-key") == "test-key"
        payload = json.loads(request.data)
        assert payload == {
            "sender": {"email": "noreply@example.com", "name": "CodeGuard"},
            "to": [{"email": "a@example.com"}],
            "subject": "Subject",
            "textContent": "Body text",
        }

    def test_provider_error_is_raised_with_its_reason(self, settings):
        connection = brevo(settings)
        error = urllib.error.HTTPError("u", 400, "Bad", {}, io.BytesIO(b'{"message":"sender not valid"}'))
        with mock.patch("core.email.urllib.request.urlopen", side_effect=error):
            with pytest.raises(EmailDeliveryError, match="sender not valid"):
                EmailMessage("S", "B", to=["a@example.com"], connection=connection).send()

    def test_fail_silently_returns_zero(self, settings):
        connection = brevo(settings, fail_silently=True)
        with mock.patch("core.email.urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            assert EmailMessage("S", "B", to=["a@example.com"], connection=connection).send() == 0

    def test_missing_key_is_a_configuration_error(self, settings):
        connection = brevo(settings)
        settings.BREVO_API_KEY = ""
        with pytest.raises(ImproperlyConfigured):
            EmailMessage("S", "B", to=["a@example.com"], connection=connection).send()

    def test_failures_are_logged_without_the_message(self, settings, caplog):
        connection = brevo(settings)
        error = urllib.error.HTTPError("u", 401, "No", {}, io.BytesIO(b"unauthorized"))
        with mock.patch("core.email.urllib.request.urlopen", side_effect=error), pytest.raises(EmailDeliveryError):
            EmailMessage("Secret subject", "secret body link", to=["a@example.com"], connection=connection).send()
        logged = caplog.text
        assert "status=401" in logged
        assert "secret" not in logged.lower() and "a@example.com" not in logged


class TestDescriptions:
    def test_backend_descriptions(self, settings):
        settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
        assert describe_backend().startswith("Not delivered") and not delivers_email()
        settings.EMAIL_BACKEND = BREVO
        settings.BREVO_API_KEY = ""
        assert "missing" in describe_backend()
        settings.BREVO_API_KEY = "k"
        assert describe_backend() == "Brevo API" and delivers_email()

    def test_deploy_check_warns_when_email_is_not_delivered(self, settings):
        from accounts.checks import email_not_delivered

        settings.DEBUG = False
        settings.EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
        assert [w.id for w in email_not_delivered(None)] == ["codeguard.W002"]
        settings.EMAIL_BACKEND = BREVO
        assert email_not_delivered(None) == []


class TestSendTestEmail:
    def test_sends_one_message(self, mailoutbox):
        out = io.StringIO()
        call_command("send_test_email", "me@example.com", stdout=out)
        assert "Sent." in out.getvalue()
        assert mailoutbox[0].to == ["me@example.com"] and "email delivery" in mailoutbox[0].body

    def test_reports_failure(self):
        with mock.patch("core.management.commands.send_test_email.EmailMessage.send", side_effect=OSError("refused")):
            with pytest.raises(CommandError, match="refused"):
                call_command("send_test_email", "me@example.com", stdout=io.StringIO())

    def test_rejects_a_bad_address(self):
        with pytest.raises(CommandError):
            call_command("send_test_email", "not-an-address", stdout=io.StringIO())


class TestLegalPages:
    @pytest.mark.parametrize("name", ["core:privacy", "core:terms", "core:contact"])
    def test_pages_are_public_and_linked_from_the_footer(self, client, name):
        assert client.get(reverse(name)).status_code == 200
        assert reverse(name) in client.get(reverse("core:landing")).content.decode()

    def test_contact_address_is_shown_when_configured(self, client, settings):
        settings.CODEGUARD_CONTACT_EMAIL = "help@example.com"
        for name in ("core:privacy", "core:contact"):
            assert "help@example.com" in client.get(reverse(name)).content.decode()

    def test_privacy_notice_names_the_email_provider_only_when_used(self, client, settings):
        assert "Brevo" not in client.get(reverse("core:privacy")).content.decode()
        settings.EMAIL_BACKEND = BREVO
        assert "Brevo" in client.get(reverse("core:privacy")).content.decode()

    def test_signed_in_users_see_the_app_layout(self, analyst_client):
        html = analyst_client.get(reverse("core:terms")).content.decode()
        assert "Terms of use" in html and "New simulation" in html
