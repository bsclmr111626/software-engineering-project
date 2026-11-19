from django.conf import settings
from django.db import models


class AuditAction(models.TextChoices):
    LOGIN = "login", "Signed in"
    LOGOUT = "logout", "Signed out"
    LOGIN_FAILED = "login_failed", "Failed sign-in"
    LOGIN_THROTTLED = "login_throttled", "Sign-in blocked (too many failures)"
    REGISTER = "register", "Registered"
    PASSWORD_CHANGE = "password_change", "Changed password"
    SCENARIO_CREATE = "scenario_create", "Created scenario"
    SCENARIO_UPDATE = "scenario_update", "Edited scenario"
    SCENARIO_ARCHIVE = "scenario_archive", "Archived scenario"
    SCENARIO_RESTORE = "scenario_restore", "Restored scenario"
    SCENARIO_DELETE = "scenario_delete", "Deleted scenario"
    SCENARIO_CLONE = "scenario_clone", "Cloned scenario"
    SIMULATION_RUN = "simulation_run", "Ran simulation"
    SIMULATION_FAILED = "simulation_failed", "Simulation failed"
    REPORT_SHARE = "report_share", "Changed report sharing"
    REPORT_EXPORT = "report_export", "Exported report"
    ROLE_CHANGE = "role_change", "Changed user role"
    AUDIT_PURGE = "audit_purge", "Purged old audit events"
    REMEDIATION_CREATE = "remediation_create", "Added to remediation plan"
    REMEDIATION_UPDATE = "remediation_update", "Updated remediation item"
    REMEDIATION_ASSIGN = "remediation_assign", "Assigned a remediation item"
    REMEDIATION_COMMENT = "remediation_comment", "Commented on a remediation item"
    PROFILE_UPDATE = "profile_update", "Updated profile"
    EMAIL_CHANGE = "email_change", "Changed email address"
    PREFERENCES_UPDATE = "preferences_update", "Updated preferences"
    SESSIONS_REVOKED = "sessions_revoked", "Signed out other sessions"
    DATA_EXPORT = "data_export", "Downloaded personal data"
    SIGNUP_REQUEST = "signup_request", "Submitted the sign-up form"
    VERIFICATION_SENT = "verification_sent", "Sent an email confirmation link"
    EMAIL_VERIFIED = "email_verified", "Confirmed email address"
    EMAIL_CHANGE_REQUEST = "email_change_request", "Requested an email change"
    PASSWORD_RESET_REQUEST = "password_reset_request", "Requested a password reset"
    PASSWORD_RESET = "password_reset", "Reset password with an emailed link"
    INVITATION_CREATE = "invitation_create", "Invited a user"
    INVITATION_RESEND = "invitation_resend", "Resent an invitation"
    INVITATION_REVOKE = "invitation_revoke", "Revoked an invitation"
    INVITATION_ACCEPT = "invitation_accept", "Accepted an invitation"
    USER_SUSPEND = "user_suspend", "Suspended a user"
    USER_REACTIVATE = "user_reactivate", "Reactivated a user"
    ACCOUNT_CLOSE = "account_close", "Closed their account"
    ACCOUNT_DELETE = "account_delete", "Deleted a closed account"
    WORKSPACE_CREATE = "workspace_create", "Created a workspace"
    WORKSPACE_UPDATE = "workspace_update", "Renamed the workspace"
    TWO_FACTOR_ENABLE = "two_factor_enable", "Turned on two-step sign-in"
    TWO_FACTOR_DISABLE = "two_factor_disable", "Turned off two-step sign-in"
    TWO_FACTOR_RESET = "two_factor_reset", "Reset a member's two-step sign-in"
    TWO_FACTOR_FAILED = "two_factor_failed", "Wrong two-step sign-in code"
    BACKUP_CODES_CREATE = "backup_codes_create", "Made new backup codes"
    BACKUP_CODE_USED = "backup_code_used", "Signed in with a backup code"
    ACCESS_REQUEST = "access_request", "Requested access"
    ACCESS_APPROVE = "access_approve", "Approved an access request"
    ACCESS_DECLINE = "access_decline", "Declined an access request"


class AppendOnlyQuerySet(models.QuerySet):
    """Refuses bulk rewrites and deletes, which bypass ``Model.save()``.

    Removing a user still works: Django's SET_NULL cascade clears ``actor``
    with a low-level update query, keeping ``actor_username`` as the record.
    Old events are removed only by the retention command
    (``purge_audit_events``), which uses ``_purge`` deliberately.
    """

    def update(self, **kwargs):
        raise ValueError("Audit events are append-only and cannot be modified.")

    def delete(self):
        raise ValueError("Audit events are append-only; use the purge_audit_events retention command.")

    def _purge(self):
        return super().delete()


class AuditEvent(models.Model):
    """An append-only record of an important action.

    Only safe context is stored (usernames, object identifiers and small
    metadata dictionaries). Passwords, tokens and session keys are never
    recorded; ``audit.services.record_event`` strips sensitive keys.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_events"
    )
    actor_username = models.CharField(max_length=150, blank=True)
    # The workspace the event belongs to, so its administrators can read it.
    # NULL for events with no account behind them (an unknown sign-in name).
    workspace = models.ForeignKey(
        "accounts.Workspace", null=True, blank=True, on_delete=models.PROTECT, related_name="audit_events"
    )
    action = models.CharField(max_length=32, choices=AuditAction.choices, db_index=True)
    object_type = models.CharField(max_length=64, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["workspace", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.actor_username or 'anonymous'} {self.action}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Audit events are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit events are append-only; use the purge_audit_events retention command.")
