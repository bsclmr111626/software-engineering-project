"""Give every owned scenario its owner's workspace.

Seeded reference scenarios have no owner and keep no workspace: they stay
readable by everyone. A scenario someone wrote (private, or shared by an
administrator) moves into that person's workspace.
"""

import django.db.models.deletion
from django.db import migrations, models


def assign_workspaces(apps, schema_editor):
    ThreatScenario = apps.get_model("threats", "ThreatScenario")
    Profile = apps.get_model("accounts", "Profile")
    Workspace = apps.get_model("accounts", "Workspace")
    default = Workspace.objects.filter(is_default=True).first()
    by_user = dict(Profile.objects.values_list("user_id", "workspace_id"))
    for scenario in ThreatScenario.objects.filter(owner__isnull=False, workspace__isnull=True):
        scenario.workspace_id = by_user.get(scenario.owner_id) or (default.pk if default else None)
        scenario.save(update_fields=["workspace"])


class Migration(migrations.Migration):
    dependencies = [
        ("threats", "0003_control_assumptions"),
        ("accounts", "0010_workspaces"),
    ]

    operations = [
        migrations.AddField(
            model_name="threatscenario",
            name="workspace",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="scenarios",
                to="accounts.workspace",
            ),
        ),
        migrations.RunPython(assign_workspaces, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="threatscenario",
            constraint=models.CheckConstraint(
                condition=models.Q(("owner__isnull", True), ("workspace__isnull", False), _connector="OR"),
                name="owned_scenario_has_workspace",
            ),
        ),
    ]
