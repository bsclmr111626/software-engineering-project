from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from audit.models import AuditAction
from audit.services import record_event

from .models import Profile, Role
from .preferences import (
    SESSION_AGENT_KEY,
    SESSION_EPOCH_KEY,
    SESSION_STARTED_KEY,
    describe_agent,
    preferences_for,
)


@receiver(post_save, sender=get_user_model())
def create_profile(sender, instance, created, **kwargs):
    if created:
        role = Role.ADMIN if instance.is_superuser else settings.CODEGUARD_DEFAULT_ROLE
        Profile.objects.get_or_create(user=instance, defaults={"role": role})


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    record_event(user, AuditAction.LOGIN, request=request)
    if request is not None and hasattr(request, "session"):
        request.session[SESSION_EPOCH_KEY] = preferences_for(user).session_epoch
        request.session[SESSION_STARTED_KEY] = timezone.now().isoformat()
        request.session[SESSION_AGENT_KEY] = describe_agent(request.META.get("HTTP_USER_AGENT"))


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        record_event(user, AuditAction.LOGOUT, request=request)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    # Only the attempted username is kept; the password is never recorded.
    username = str(credentials.get("username", ""))[:150]
    record_event(None, AuditAction.LOGIN_FAILED, request=request, attempted_username=username)
