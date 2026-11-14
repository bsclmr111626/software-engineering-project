"""Email delivery through Brevo's HTTPS API.

PythonAnywhere's free plan blocks outbound SMTP but allows api.brevo.com, so
production mail goes over HTTPS. Select it with
``DJANGO_EMAIL_BACKEND=core.email.BrevoEmailBackend`` and ``BREVO_API_KEY``.
Any other Django backend (console, SMTP) keeps working unchanged.

Logs never contain message bodies, links or recipient addresses: only the
provider's status code and the number of recipients.
"""

import json
import logging
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger("codeguard.email")

BREVO_ENDPOINT = "https://api.brevo.com/v3/smtp/email"


class EmailDeliveryError(Exception):
    """The provider refused or could not be reached."""


def _address(value):
    name, email = parseaddr(value)
    return {"email": email, "name": name} if name else {"email": email}


class BrevoEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        api_key = settings.BREVO_API_KEY
        if not api_key:
            raise ImproperlyConfigured("BREVO_API_KEY must be set to send email through Brevo.")
        sent = 0
        for message in email_messages:
            try:
                self._send(message, api_key)
            except Exception:
                if not self.fail_silently:
                    raise
            else:
                sent += 1
        return sent

    def _send(self, message, api_key):
        recipients = message.recipients()
        if not recipients:
            return
        payload = {
            "sender": _address(message.from_email or settings.DEFAULT_FROM_EMAIL),
            "to": [_address(a) for a in message.to] or [_address(a) for a in recipients],
            "subject": message.subject,
            "textContent": message.body,
        }
        if message.cc:
            payload["cc"] = [_address(a) for a in message.cc]
        if message.bcc:
            payload["bcc"] = [_address(a) for a in message.bcc]
        if message.reply_to:
            payload["replyTo"] = _address(message.reply_to[0])
        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                payload["htmlContent"] = content
        request = urllib.request.Request(
            BREVO_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={"api-key": api_key, "content-type": "application/json", "accept": "application/json"},
            method="POST",
        )
        try:
            # The URL is the fixed https endpoint above, never user input.
            with urllib.request.urlopen(request, timeout=settings.EMAIL_TIMEOUT) as response:  # noqa: S310
                status = response.status
        except urllib.error.HTTPError as error:
            # Brevo's error body names the problem (e.g. an unverified sender);
            # it never contains the message, so it is safe to surface.
            detail = error.read(300).decode("utf-8", "replace")
            logger.error("email delivery failed provider=brevo status=%s recipients=%d", error.code, len(recipients))
            raise EmailDeliveryError(f"Brevo refused the message (HTTP {error.code}): {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            logger.error(
                "email delivery failed provider=brevo error=%s recipients=%d", type(error).__name__, len(recipients)
            )
            raise EmailDeliveryError(f"Could not reach Brevo: {type(error).__name__}") from None
        logger.info("email sent provider=brevo status=%s recipients=%d", status, len(recipients))


def describe_backend():
    """A plain description of where email goes, for the Organization page."""
    backend = settings.EMAIL_BACKEND
    if backend == "core.email.BrevoEmailBackend":
        return "Brevo API" if settings.BREVO_API_KEY else "Brevo API, but BREVO_API_KEY is missing"
    if backend.endswith("smtp.EmailBackend"):
        return f"SMTP via {settings.EMAIL_HOST}"
    if backend.endswith("console.EmailBackend"):
        return "Not delivered: printed to the server log (console backend)"
    if backend.endswith("locmem.EmailBackend"):
        return "Not delivered: kept in memory (tests)"
    if backend.endswith("dummy.EmailBackend"):
        return "Not delivered: discarded (dummy backend)"
    return backend


def delivers_email():
    """False for backends that only print or discard mail. The in-memory test
    backend counts as delivering, since tests stand in for a real provider."""
    backend = settings.EMAIL_BACKEND
    return not backend.endswith(("console.EmailBackend", "dummy.EmailBackend", "filebased.EmailBackend"))
