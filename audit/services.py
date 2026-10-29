import logging

from .models import AuditEvent

logger = logging.getLogger("codeguard.audit")

SENSITIVE_KEY_PARTS = ("password", "secret", "token", "session", "csrf", "key", "credential")
MAX_VALUE_LENGTH = 200


def sanitize_metadata(metadata):
    """Drop sensitive keys and truncate long values before storage."""
    clean = {}
    for key, value in metadata.items():
        if any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
            continue
        if isinstance(value, (list, tuple)):
            value = [str(v)[:MAX_VALUE_LENGTH] for v in value][:50]
        elif not isinstance(value, (int, float, bool)) and value is not None:
            value = str(value)[:MAX_VALUE_LENGTH]
        clean[key] = value
    return clean


def client_ip(request):
    if request is None:
        return None
    # REMOTE_ADDR only: X-Forwarded-For is client-controlled unless a trusted
    # proxy is configured, so it is not trusted here.
    return request.META.get("REMOTE_ADDR") or None


def record_event(actor, action, target=None, request=None, **metadata):
    authenticated = actor is not None and getattr(actor, "is_authenticated", False)
    event = AuditEvent.objects.create(
        actor=actor if authenticated else None,
        actor_username=actor.get_username() if authenticated else "",
        action=action,
        object_type=target.__class__.__name__ if target is not None else "",
        object_id=str(target.pk)[:64] if target is not None else "",
        object_repr=str(target)[:200] if target is not None else "",
        metadata=sanitize_metadata(metadata),
        ip_address=client_ip(request),
    )
    logger.info("audit action=%s actor=%s object=%s", action, event.actor_username or "-", event.object_id or "-")
    return event
