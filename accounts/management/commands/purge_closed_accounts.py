"""Delete accounts whose owners closed them more than N days ago.

Closing an account is reversible; this command is what makes it final. Run it
on a schedule (and it runs at every release, see scripts/release.sh):

    python manage.py purge_closed_accounts            # uses CODEGUARD_ACCOUNT_DELETION_DAYS
    python manage.py purge_closed_accounts --dry-run
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts import closure


class Command(BaseCommand):
    help = "Permanently delete accounts closed by their owners more than --days ago."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, days, dry_run, **options):
        days = settings.CODEGUARD_ACCOUNT_DELETION_DAYS if days is None else days
        if days < 1:
            raise CommandError("--days must be at least 1.")
        due = list(closure.due_for_deletion(days).select_related("profile"))
        if dry_run:
            self.stdout.write(f"{len(due)} closed account(s) older than {days} days would be deleted.")
            return
        for user in due:
            closure.delete_closed(user)
        self.stdout.write(self.style.SUCCESS(f"Deleted {len(due)} closed account(s) older than {days} days."))
