"""Two-step sign-in: time-based one-time codes (RFC 6238) and backup codes.

The codes are computed here with the standard library (HMAC-SHA1, 30-second
steps, six digits), which is what every authenticator app (Google
Authenticator, Microsoft Authenticator, 1Password, Aegis...) expects.

Signing in with it on is two requests. The password step (accounts/views.
SignInView) does not sign the person in; it stores a short-lived "pending"
marker in the session and sends them to the code step (accounts/views.
two_factor_challenge), which signs them in only after a correct code. Wrong
codes are audited and limited like wrong passwords.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import datetime, timedelta
from urllib.parse import quote, urlencode

import segno
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html

from audit.models import AuditAction, AuditEvent

from .models import BackupCode, TwoFactorDevice

STEP_SECONDS = 30
DIGITS = 6
# Codes from one step before or after are accepted too, for clocks that drift.
DRIFT_STEPS = 1
BACKUP_CODE_COUNT = 10
BACKUP_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O or 1/I/L to misread
BACKUP_CODE_LENGTH = 10

PENDING_KEY = "cg_two_factor_pending"
SETUP_KEY = "cg_two_factor_setup_secret"
CODES_KEY = "cg_two_factor_new_codes"
PENDING_MINUTES = 5


# One-time codes ----------------------------------------------------------


def new_secret():
    """A random 160-bit key, base32 without padding (what apps accept)."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret):
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def code_at(secret, step):
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def current_step(now=None):
    return int((now if now is not None else time.time()) // STEP_SECONDS)


def _clean(code):
    return "".join(ch for ch in str(code or "") if ch.isalnum()).upper()


def matching_step(secret, code, after_step=None, now=None):
    """The time step ``code`` belongs to, or None. Steps at or before
    ``after_step`` are refused, so a code cannot be used twice."""
    code = _clean(code)
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for candidate in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):
        if after_step is not None and candidate <= after_step:
            continue
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(user, secret):
    issuer = "CodeGuard"
    label = quote(f"{issuer}:{user.get_username()}")
    query = urlencode({"secret": secret, "issuer": issuer, "digits": DIGITS, "period": STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"


def grouped(secret):
    """The key in groups of four, for typing it into an app by hand."""
    return " ".join(secret[i : i + 4] for i in range(0, len(secret), 4))


def qr_svg(text):
    """An inline SVG QR code drawn with the --qr-* tokens (never literal
    colours). Each dark module run on a row becomes one rectangle."""
    qr = segno.make(text, error="m")
    matrix = [list(row) for row in qr.matrix]
    border = 4
    size = len(matrix) + 2 * border
    runs = []
    for y, row in enumerate(matrix):
        x = 0
        while x < len(row):
            if row[x]:
                start = x
                while x < len(row) and row[x]:
                    x += 1
                runs.append(f"M{start + border} {y + border}h{x - start}v1h-{x - start}z")
            else:
                x += 1
    return format_html(
        '<svg class="cg-qr" viewBox="0 0 {} {}" role="img" aria-label="QR code for your authenticator app" '
        'shape-rendering="crispEdges"><rect class="cg-qr-light" width="{}" height="{}"/>'
        '<path class="cg-qr-dark" d="{}"/></svg>',
        size,
        size,
        size,
        size,
        "".join(runs),
    )


# Devices and backup codes ------------------------------------------------


def device_for(user):
    if user is None or not getattr(user, "pk", None):
        return None
    return TwoFactorDevice.objects.filter(user=user).first()


def enabled(user):
    return device_for(user) is not None


def _hash(code):
    return hashlib.sha256(_clean(code).encode("ascii")).hexdigest()


def _new_code():
    raw = "".join(secrets.choice(BACKUP_ALPHABET) for _ in range(BACKUP_CODE_LENGTH))
    return f"{raw[:5]}-{raw[5:]}"


@transaction.atomic
def new_backup_codes(user):
    """Replaces the user's backup codes and returns the new ones in plain text
    (the only time they exist outside the person's own copy)."""
    BackupCode.objects.filter(user=user).delete()
    codes = [_new_code() for _ in range(BACKUP_CODE_COUNT)]
    BackupCode.objects.bulk_create([BackupCode(user=user, code_hash=_hash(c)) for c in codes])
    return codes


def backup_codes_left(user):
    return BackupCode.objects.filter(user=user, used_at__isnull=True).count()


@transaction.atomic
def enable(user, secret, step):
    device, _ = TwoFactorDevice.objects.update_or_create(
        user=user,
        defaults={
            "secret": secret,
            "confirmed_at": timezone.now(),
            "last_used_step": step,
            "last_used_at": timezone.now(),
        },
    )
    return device, new_backup_codes(user)


@transaction.atomic
def disable(user):
    TwoFactorDevice.objects.filter(user=user).delete()
    BackupCode.objects.filter(user=user).delete()


def verify(user, code):
    """Checks a sign-in code. Returns "totp", "backup" or None.

    A one-time code moves ``last_used_step`` forward under a row lock, so two
    requests racing with the same code cannot both succeed. A backup code is
    marked used the same way.
    """
    cleaned = _clean(code)
    with transaction.atomic():
        device = TwoFactorDevice.objects.select_for_update().filter(user=user).first()
        if device is None:
            return None
        if len(cleaned) == DIGITS and cleaned.isdigit():
            step = matching_step(device.secret, cleaned, after_step=device.last_used_step)
            if step is None:
                return None
            device.last_used_step = step
            device.last_used_at = timezone.now()
            device.save(update_fields=["last_used_step", "last_used_at"])
            return "totp"
        if len(cleaned) == BACKUP_CODE_LENGTH:
            used = BackupCode.objects.filter(user=user, code_hash=_hash(cleaned), used_at__isnull=True).update(
                used_at=timezone.now()
            )
            if used:
                return "backup"
    return None


# The sign-in step ---------------------------------------------------------


def begin(request, user, redirect_to):
    """Remembers that ``user`` gave the right password; no sign-in yet."""
    request.session.cycle_key()
    request.session[PENDING_KEY] = {
        "user_id": user.pk,
        "backend": getattr(user, "backend", settings.AUTHENTICATION_BACKENDS[0]),
        "next": redirect_to,
        "started": timezone.now().isoformat(),
        # Changing the password (for example after a reset) voids a pending step.
        "password": user.password[-16:],
    }


def pending(request):
    """The pending sign-in (dict) if one exists and has not expired."""
    data = request.session.get(PENDING_KEY)
    if not data:
        return None
    started = datetime.fromisoformat(data["started"])
    if timezone.now() - started > timedelta(minutes=PENDING_MINUTES):
        clear(request)
        return None
    return data


def clear(request):
    request.session.pop(PENDING_KEY, None)


def failures(user):
    """Wrong codes for ``user`` since their last sign-in, within the lockout window."""
    since = timezone.now() - timedelta(minutes=settings.CODEGUARD_LOGIN_LOCKOUT_MINUTES)
    events = AuditEvent.objects.filter(action=AuditAction.TWO_FACTOR_FAILED, actor=user, created_at__gte=since)
    last_login = (
        AuditEvent.objects.filter(action=AuditAction.LOGIN, actor=user)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
    )
    if last_login:
        events = events.filter(id__gt=last_login)
    return events.count()


def is_locked(user):
    return failures(user) >= settings.CODEGUARD_LOGIN_MAX_FAILURES
