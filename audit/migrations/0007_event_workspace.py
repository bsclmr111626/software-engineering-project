"""Record which workspace each audit event belongs to.

Existing events get the workspace of the account that performed them.
Events with no account behind them (failed sign-ins for unknown names,
sign-up requests) stay without one.

The append-only triggers (audit/integrity.py) would refuse this backfill,
so they are dropped first; they are re-created, with the new column
protected too, when ``migrate`` finishes.
"""

import django.db.models.deletion
from django.db import migrations, models


def drop_triggers(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        schema_editor.execute("DROP TRIGGER IF EXISTS audit_event_no_update")
        schema_editor.execute("DROP TRIGGER IF EXISTS audit_event_no_early_delete")


def assign_workspaces(apps, schema_editor):
    AuditEvent = apps.get_model("audit", "AuditEvent")
    Profile = apps.get_model("accounts", "Profile")
    for user_id, workspace_id in Profile.objects.values_list("user_id", "workspace_id"):
        AuditEvent.objects.filter(actor_id=user_id, workspace__isnull=True).update(workspace_id=workspace_id)


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0006_account_closure"),
        ("accounts", "0010_workspaces"),
    ]

    operations = [
        migrations.RunPython(drop_triggers, migrations.RunPython.noop),
        migrations.AddField(
            model_name="auditevent",
            name="workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="audit_events",
                to="accounts.workspace",
            ),
        ),
        migrations.RunPython(drop_triggers, migrations.RunPython.noop),
        migrations.RunPython(assign_workspaces, migrations.RunPython.noop),
    ]
