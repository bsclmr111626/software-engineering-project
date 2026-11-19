"""Delete access requests that were approved or declined more than N days ago.

Requests hold a name, an email address and a free-text reason from someone
who may never get an account, so they are not kept once dealt with. Waiting
requests are never deleted. It runs at every release (scripts/release.sh):

    python manage.py purge_access_requests            # uses CODEGUARD_ACCESS_REQUEST_DAYS
    python manage.py purge_access_requests --dry-run
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts import access_requests


class Command(BaseCommand):
    help = "Permanently delete access requests reviewed more than --days ago."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, days, dry_run, **options):
        days = settings.CODEGUARD_ACCESS_REQUEST_DAYS if days is None else days
        if days < 1:
            raise CommandError("--days must be at least 1.")
        due = access_requests.due_for_deletion(days)
        if dry_run:
            self.stdout.write(f"{due.count()} reviewed access request(s) older than {days} days would be deleted.")
            return
        deleted, _ = due.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted} reviewed access request(s) older than {days} days."))
