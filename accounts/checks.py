"""Deployment checks surfaced by ``manage.py check --deploy`` (and CI)."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def open_registration(app_configs, **kwargs):
    if settings.DEBUG or settings.CODEGUARD_REGISTRATION != "open":
        return []
    return [
        Warning(
            "Self-registration is open: anyone who can reach this deployment can create an Analyst account "
            "and read every shared scenario and report.",
            hint="Set CODEGUARD_REGISTRATION=domain (with CODEGUARD_REGISTRATION_DOMAINS) or closed.",
            id="codeguard.W001",
        )
    ]


@register(Tags.security, deploy=True)
def email_not_delivered(app_configs, **kwargs):
    from core.email import delivers_email

    if settings.DEBUG or delivers_email():
        return []
    return [
        Warning(
            "Email is not delivered (console, in-memory or dummy backend): password reset links, email "
            "confirmation and invitations cannot reach anyone.",
            hint="Set DJANGO_EMAIL_BACKEND=core.email.BrevoEmailBackend and BREVO_API_KEY, or an SMTP backend.",
            id="codeguard.W002",
        )
    ]
