"""Signed links that prove someone can read an email address.

A token carries the user id, the address being confirmed and a fingerprint
of the account state that the confirmation changes (the verified time, the
pending address and the password hash). Once the link is used that state
changes, so the same link stops working: single use without storing tokens.
Tokens expire after CODEGUARD_EMAIL_VERIFICATION_HOURS and are signed with
SECRET_KEY, so they cannot be forged or edited.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.utils.crypto import constant_time_compare, salted_hmac

SALT = "codeguard.accounts.email-confirmation"


def _fingerprint(user, email):
    profile = user.profile
    state = "|".join(
        [
            str(user.pk),
            email.lower(),
            (user.email or "").lower(),
            profile.pending_email.lower(),
            profile.email_verified_at.isoformat() if profile.email_verified_at else "",
            user.password,
        ]
    )
    return salted_hmac(SALT, state).hexdigest()[:32]


def make_token(user, email):
    return signing.dumps({"u": user.pk, "e": email.lower(), "f": _fingerprint(user, email)}, salt=SALT, compress=True)


def read_token(token):
    """Return (user, email) for a valid, unexpired, unused token, else None."""
    try:
        data = signing.loads(token, salt=SALT, max_age=settings.CODEGUARD_EMAIL_VERIFICATION_HOURS * 3600)
    except signing.BadSignature:  # includes SignatureExpired
        return None
    if not isinstance(data, dict):
        return None
    user = get_user_model().objects.select_related("profile").filter(pk=data.get("u"), is_active=True).first()
    email = data.get("e") or ""
    if user is None or not constant_time_compare(_fingerprint(user, email), data.get("f", "")):
        return None
    if email not in ((user.email or "").lower(), user.profile.pending_email.lower()):
        return None
    return user, email


def email_fingerprint(email):
    """A keyed hash of an address for audit metadata and rate limits, so the
    audit log can count requests per address without storing the address."""
    return salted_hmac("codeguard.accounts.email-fingerprint", email.strip().lower()).hexdigest()[:24]
