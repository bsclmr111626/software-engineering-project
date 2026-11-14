"""Send one test message to check that this deployment can deliver email.

python manage.py send_test_email you@example.com
"""

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.template.loader import render_to_string

from core.email import describe_backend


class Command(BaseCommand):
    help = "Send a test email through the configured backend and report the result."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Recipient address")

    def handle(self, *args, to, **options):
        try:
            validate_email(to)
        except Exception:
            raise CommandError(f"{to!r} is not a valid email address.") from None
        self.stdout.write(f"Backend: {describe_backend()}")
        self.stdout.write(f"From: {settings.DEFAULT_FROM_EMAIL}")
        context = {"site_name": "CodeGuard"}
        message = EmailMessage(
            subject=render_to_string("emails/test_subject.txt", context).strip(),
            body=render_to_string("emails/test.txt", context),
            to=[to],
        )
        try:
            message.send(fail_silently=False)
        except Exception as error:
            raise CommandError(f"Not sent: {error}") from None
        self.stdout.write(self.style.SUCCESS("Sent. Check the inbox (and the spam folder) of the recipient."))
