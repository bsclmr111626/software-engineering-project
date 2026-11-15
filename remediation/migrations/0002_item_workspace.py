"""Give every remediation item the workspace of the person who added it, so
items shared with a team stay inside that workspace."""

import django.db.models.deletion
from django.db import migrations, models


def assign_workspaces(apps, schema_editor):
    RemediationItem = apps.get_model("remediation", "RemediationItem")
    Profile = apps.get_model("accounts", "Profile")
    Workspace = apps.get_model("accounts", "Workspace")
    default = Workspace.objects.filter(is_default=True).first()
    by_user = dict(Profile.objects.values_list("user_id", "workspace_id"))
    for owner_id in RemediationItem.objects.filter(workspace__isnull=True).values_list("owner_id", flat=True).distinct():
        workspace_id = by_user.get(owner_id) or (default.pk if default else None)
        RemediationItem.objects.filter(owner_id=owner_id, workspace__isnull=True).update(workspace_id=workspace_id)


class Migration(migrations.Migration):
    dependencies = [
        ("remediation", "0001_initial"),
        ("accounts", "0012_two_factor"),
    ]

    operations = [
        migrations.AddField(
            model_name="remediationitem",
            name="workspace",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="remediation_items",
                to="accounts.workspace",
            ),
        ),
        migrations.RunPython(assign_workspaces, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="remediationitem",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="remediation_items",
                to="accounts.workspace",
            ),
        ),
    ]
