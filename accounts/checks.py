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
