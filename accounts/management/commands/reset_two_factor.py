from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts import two_factor
from audit.models import AuditAction
from audit.services import record_event


class Command(BaseCommand):
    help = (
        "Turn off two-step sign-in for an account whose owner lost their authenticator app and backup "
        "codes. Confirm who is asking first. Workspace administrators can do the same from Settings."
    )

    def add_arguments(self, parser):
        parser.add_argument("username")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"]).first()
        if user is None:
            raise CommandError(f"No account named {options['username']!r}.")
        if not two_factor.enabled(user):
            self.stdout.write(f"Two-step sign-in is already off for {user.get_username()}.")
            return
        two_factor.disable(user)
        record_event(None, AuditAction.TWO_FACTOR_RESET, target=user, via="manage.py reset_two_factor")
        self.stdout.write(self.style.SUCCESS(f"Two-step sign-in is off for {user.get_username()}."))
