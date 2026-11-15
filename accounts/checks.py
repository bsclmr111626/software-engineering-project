"""Deployment checks surfaced by ``manage.py check --deploy`` (and CI)."""

from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def open_registration(app_configs, **kwargs):
    """Open sign-up needs working email: an account cannot sign in until it
    confirms its address, so without delivery nobody could finish signing up.
    (Each sign-up gets its own workspace, so open sign-up no longer exposes
    other people's shared work.)"""
    from core.email import delivers_email

    if settings.DEBUG or settings.CODEGUARD_REGISTRATION == "closed" or delivers_email():
        return []
    return [
        Warning(
            "Self-registration is enabled but email is not delivered, so new accounts can never confirm "
            "their address and sign in.",
            hint="Configure email delivery, or set CODEGUARD_REGISTRATION=closed until it works.",
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
