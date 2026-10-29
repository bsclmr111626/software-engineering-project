"""Retention: delete audit events older than a cut-off.

The audit log is append-only during normal operation. This command is the one
sanctioned way to remove history, so it is explicit about the cut-off, refuses
very short retention, and records its own run as an audit event.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from audit.models import AuditAction, AuditEvent
from audit.services import record_event

MINIMUM_DAYS = 30


class Command(BaseCommand):
    help = "Delete audit events older than --days (default 365). Use --dry-run to only count them."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=365)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, days, dry_run, **options):
        if days < MINIMUM_DAYS:
            raise CommandError(f"Retention shorter than {MINIMUM_DAYS} days is refused.")
        cutoff = timezone.now() - timedelta(days=days)
        old = AuditEvent.objects.filter(created_at__lt=cutoff)
        count = old.count()
        if dry_run:
            self.stdout.write(f"{count} audit event(s) older than {days} days would be deleted.")
            return
        old._purge()
        record_event(None, AuditAction.AUDIT_PURGE, retention_days=days, deleted=count)
        self.stdout.write(self.style.SUCCESS(f"Deleted {count} audit event(s) older than {days} days."))
