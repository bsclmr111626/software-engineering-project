"""Introduce workspaces.

Everything that existed before this migration belonged to one implicit
team, so it all moves into one workspace, marked as the default. Nothing is
deleted and nobody loses access to anything they could see before.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

DEFAULT_NAME = "CodeGuard"


def create_default_workspace(apps, schema_editor):
    Workspace = apps.get_model("accounts", "Workspace")
    Profile = apps.get_model("accounts", "Profile")
    Invitation = apps.get_model("accounts", "Invitation")
    workspace = Workspace.objects.filter(is_default=True).first()
    if workspace is None:
        workspace = Workspace.objects.create(name=DEFAULT_NAME, is_default=True)
    Profile.objects.filter(workspace__isnull=True).update(workspace=workspace)
    Invitation.objects.filter(workspace__isnull=True).update(workspace=workspace)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_account_closure"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Workspace",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="workspaces_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["name", "id"]},
        ),
        migrations.AddConstraint(
            model_name="workspace",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_default", True)), fields=("is_default",), name="one_default_workspace"
            ),
        ),
        migrations.AddField(
            model_name="profile",
            name="workspace",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="profiles",
                to="accounts.workspace",
            ),
        ),
        migrations.AddField(
            model_name="invitation",
            name="workspace",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invitations",
                to="accounts.workspace",
            ),
        ),
        # Reversing drops the columns and the table, so there is nothing to undo here.
        migrations.RunPython(create_default_workspace, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="profile",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT, related_name="profiles", to="accounts.workspace"
            ),
        ),
        migrations.AlterField(
            model_name="invitation",
            name="workspace",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="invitations", to="accounts.workspace"
            ),
        ),
    ]
