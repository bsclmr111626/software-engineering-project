"""Give every simulation run the workspace of the person who ran it, so a
shared report is visible inside that workspace only."""

import django.db.models.deletion
from django.db import migrations, models


def assign_workspaces(apps, schema_editor):
    SimulationRun = apps.get_model("simulation", "SimulationRun")
    Profile = apps.get_model("accounts", "Profile")
    Workspace = apps.get_model("accounts", "Workspace")
    default = Workspace.objects.filter(is_default=True).first()
    by_user = dict(Profile.objects.values_list("user_id", "workspace_id"))
    for user_id in SimulationRun.objects.filter(workspace__isnull=True).values_list("user_id", flat=True).distinct():
        workspace_id = by_user.get(user_id) or (default.pk if default else None)
        SimulationRun.objects.filter(user_id=user_id, workspace__isnull=True).update(workspace_id=workspace_id)


class Migration(migrations.Migration):
    dependencies = [
        ("simulation", "0001_initial"),
        ("accounts", "0010_workspaces"),
    ]

    operations = [
        migrations.AddField(
            model_name="simulationrun",
            name="workspace",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="simulation_runs",
                to="accounts.workspace",
            ),
        ),
        migrations.RunPython(assign_workspaces, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="simulationrun",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="simulation_runs",
                to="accounts.workspace",
            ),
        ),
    ]
