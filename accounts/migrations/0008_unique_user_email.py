"""Make email addresses unique, ignoring case, so an address identifies one
account (needed for sign-in by email, password reset and invitations).

The built-in user table belongs to django.contrib.auth, so the rule is a
database index created here rather than a model constraint. Empty emails are
allowed more than once. The migration stops with a list of the conflicting
addresses if existing data would break the rule; nothing is changed then.
"""

from django.conf import settings
from django.db import migrations
from django.db.models import Count
from django.db.models.functions import Lower

INDEX = "accounts_user_email_ci_unique"


def check_duplicates(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    duplicates = (
        User.objects.exclude(email="")
        .annotate(address=Lower("email"))
        .values("address")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .values_list("address", flat=True)
    )
    if duplicates:
        raise RuntimeError(
            "These email addresses are used by more than one account: "
            + ", ".join(sorted(duplicates))
            + ". Give each account its own address (Django admin > Users), then run migrate again."
        )


def create_index(apps, schema_editor):
    table = schema_editor.quote_name(apps.get_model(*settings.AUTH_USER_MODEL.split("."))._meta.db_table)
    schema_editor.execute(f"CREATE UNIQUE INDEX {INDEX} ON {table} (LOWER(email)) WHERE email <> ''")


def drop_index(apps, schema_editor):
    schema_editor.execute(f"DROP INDEX IF EXISTS {INDEX}")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_account_lifecycle"),
        # The latest auth migration, not just "auth __first__": on a fresh SQLite
        # database the later auth migrations rebuild auth_user, which drops this index.
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(check_duplicates, migrations.RunPython.noop),
        migrations.RunPython(create_index, drop_index),
    ]
