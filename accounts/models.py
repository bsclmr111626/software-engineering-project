from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Role(models.TextChoices):
    ADMIN = "admin", "Administrator"
    ANALYST = "analyst", "Analyst"
    VIEWER = "viewer", "Viewer"


class AccountOrigin(models.TextChoices):
    ADMIN = "admin", "Created by an administrator"
    SIGNUP = "signup", "Self-registration"
    INVITATION = "invitation", "Invitation"


class Profile(models.Model):
    """Stores the CodeGuard role of a user (one profile per user), the state
    of their email address, and the optional professional details shown on
    their profile page.

    ``email_verified_at`` is set only when the person opened a link sent to
    ``user.email`` (verification, invitation or password reset). Self-registered
    accounts cannot sign in until it is set. ``pending_email`` holds a new
    address until its confirmation link is opened.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.VIEWER)
    origin = models.CharField(max_length=12, choices=AccountOrigin.choices, default=AccountOrigin.ADMIN)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    pending_email = models.EmailField(blank=True)
    job_title = models.CharField(max_length=80, blank=True)
    team = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(role__in=Role.values), name="profile_role_valid"),
        ]

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"

    @property
    def email_verified(self):
        return self.email_verified_at is not None

    @property
    def must_verify_before_sign_in(self):
        return self.origin == AccountOrigin.SIGNUP and not self.email_verified


class ColorMode(models.TextChoices):
    SYSTEM = "system", "Match my device"
    LIGHT = "light", "Light"
    DARK = "dark", "Dark"


class Accent(models.TextChoices):
    ULTRAMARINE = "ultramarine", "Ultramarine"
    IRIS = "iris", "Iris"
    GRAPHITE = "graphite", "Graphite"


class Surface(models.TextChoices):
    PAPER = "paper", "Paper"
    PEARL = "pearl", "Pearl"
    SAGE = "sage", "Sage"


class TextSize(models.TextChoices):
    SMALL = "small", "Small"
    DEFAULT = "default", "Default"
    LARGE = "large", "Large"
    LARGER = "larger", "Larger"


class HeadingFont(models.TextChoices):
    SERIF = "serif", "Editorial serif"
    SANS = "sans", "Sans-serif"


class Density(models.TextChoices):
    COMFORTABLE = "comfortable", "Comfortable"
    COMPACT = "compact", "Compact"


class TimestampStyle(models.TextChoices):
    RELATIVE = "relative", "Relative (3 hours ago)"
    ABSOLUTE = "absolute", "Absolute (2026-10-28 14:05)"


class StartPage(models.TextChoices):
    OVERVIEW = "overview", "Overview"
    SUPPLY_CHAIN = "supply_chain", "Supply chain"
    SIMULATIONS = "simulations", "Simulations"
    REPORTS = "reports", "Reports"


PAGE_SIZES = [(10, "10 rows"), (25, "25 rows"), (50, "50 rows")]


class UserPreference(models.Model):
    """Per-user interface and notification preferences.

    Every field changes real behaviour: appearance values are rendered as
    attributes on <html> (read by the CSS tokens), display values are read by
    the views that paginate and format timestamps, notification values filter
    the in-app notification feed, and ``session_epoch`` is compared with the
    value stored in each session to sign out other sessions on request.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="preferences")

    color_mode = models.CharField(max_length=8, choices=ColorMode.choices, default=ColorMode.SYSTEM)
    accent = models.CharField(max_length=12, choices=Accent.choices, default=Accent.ULTRAMARINE)
    surface = models.CharField(max_length=8, choices=Surface.choices, default=Surface.PAPER)

    text_size = models.CharField(max_length=8, choices=TextSize.choices, default=TextSize.DEFAULT)
    heading_font = models.CharField(max_length=8, choices=HeadingFont.choices, default=HeadingFont.SERIF)

    density = models.CharField(max_length=12, choices=Density.choices, default=Density.COMFORTABLE)
    timestamp_style = models.CharField(max_length=8, choices=TimestampStyle.choices, default=TimestampStyle.RELATIVE)
    page_size = models.PositiveSmallIntegerField(choices=PAGE_SIZES, default=25)
    start_page = models.CharField(max_length=16, choices=StartPage.choices, default=StartPage.OVERVIEW)

    reduce_motion = models.BooleanField(default=False)
    increase_contrast = models.BooleanField(default=False)
    underline_links = models.BooleanField(default=False)

    notify_shared_reports = models.BooleanField(default=True)
    notify_remediation_due = models.BooleanField(default=True)
    notify_account_security = models.BooleanField(default=True)
    notifications_seen_at = models.DateTimeField(null=True, blank=True)

    share_reports_by_default = models.BooleanField(default=False)

    session_epoch = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(page_size__in=[10, 25, 50]), name="preference_page_size_valid"),
        ]

    def __str__(self):
        return f"Preferences of {self.user.get_username()}"


class Invitation(models.Model):
    """An administrator's invitation to create an account with a given role.

    Only a SHA-256 hash of the token is stored, so the database alone cannot
    be used to accept an invitation. A link works once (``accepted_at``), can
    be revoked, and expires at ``expires_at``. Resending replaces the token,
    which invalidates the previous link.
    """

    email = models.EmailField()
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.ANALYST)
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="invitations_sent"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="invitation"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="one_open_invitation_per_email",
                violation_error_message="There is already an open invitation for this address.",
            ),
            models.CheckConstraint(condition=models.Q(role__in=Role.values), name="invitation_role_valid"),
        ]

    def __str__(self):
        return f"Invitation for {self.email} ({self.get_role_display()})"

    @property
    def status(self):
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= timezone.now():
            return "expired"
        return "pending"

    @property
    def is_open(self):
        return self.status == "pending"
