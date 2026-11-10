# Database and migrations

CodeGuard stores everything in one SQLite file through the Django ORM. This document explains
the database configuration and the data model, then teaches Django migrations using CodeGuard's
own 15 migration files. Inventories: [models and tables](references/models-and-tables.md),
[migrations](references/migrations.md); diagram: [ERD](diagrams/erd.md).

Everything marked "verified" below was run on 2026-11-10 against a scratch database
(`DJANGO_DB_PATH` pointed at a temporary file), never against the developer's `db.sqlite3`.

## Part 1 — The database

### 1.1 SQLite and how CodeGuard configures it

**What it is.** SQLite is an embedded SQL database: a library inside the Python process that
reads and writes one file. There is no database server.

**Why CodeGuard uses it.** The project is an academic, single-team tool. SQLite ships with
Python, needs no installation and makes the whole application one directory plus one file.
`codeguard/settings.py` points to `docs/architecture.md` ("Database: SQLite now, PostgreSQL
when") for the recorded decision.

**How it is configured** (`codeguard/settings.py`):

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DJANGO_DB_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {
            "transaction_mode": "IMMEDIATE",
            "timeout": 20,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON",
        },
    }
}
```

| Option | Effect |
|---|---|
| `journal_mode=WAL` | Write-ahead log: readers keep reading while one writer commits. Creates `-wal` and `-shm` side files. Verified: `PRAGMA journal_mode` returns `wal`. |
| `transaction_mode: IMMEDIATE` | A transaction takes the write lock when it begins, so two writers queue instead of failing halfway with "database is locked". |
| `timeout: 20` | A waiting writer waits up to 20 s. |
| `synchronous=NORMAL` | The usual durability level for WAL. |
| `foreign_keys=ON` | Foreign keys are enforced by SQLite. |

`core/tests/test_core.py::test_sqlite_runs_in_wal_mode_with_immediate_transactions` checks this.

**Limitations.** One writer at a time; all workers must run on the host that holds the file;
no network access to the database; `backup_db` refuses any other engine. The settings are
generic Django, so a move to PostgreSQL would be a settings change plus data migration, but
that path is **not implemented or tested**.

### 1.2 Data model in one page

Twelve CodeGuard models in five apps (13 tables, because `SecurityControl.stages` adds a join
table), on top of Django's `auth.User`.

* **Reference data** (`threats`): `SupplyChainStage` (5 rows, seeded), `SecurityControl`
  (14 rows, seeded) with an M2M to stages.
* **Scenarios** (`threats`): `ThreatScenario` → `PropagationRule` (edges) and
  `ScenarioControl` (relevant controls). Six system scenarios are seeded.
* **Runs** (`simulation`): `SimulationRun` (UUID key) → `SimulationStageResult`,
  `PropagationEvent`.
* **Follow-up** (`remediation`): `RemediationItem`.
* **People** (`accounts`): `Profile` (role), `UserPreference`.
* **History** (`audit`): `AuditEvent`.

Three modelling choices are worth understanding before reading the migrations:

1. **Integrity in the schema, not only in forms.** Ranges, uniqueness and the "no self-loop"
   rule are `CheckConstraint`/`UniqueConstraint` objects in `Meta.constraints`, so the database
   refuses bad rows even if a code path skips form validation
   (`threats/tests/test_scenarios.py::TestConstraints`).
2. **Denormalised history.** Runs copy `scenario_name`, `scenario_slug`, `scenario_version`
   and store stage keys/names as text, so `on_delete=SET_NULL` on `scenario` loses nothing.
3. **A partial unique constraint.** `RemediationItem` allows only one *active* item per owner,
   scenario and control:

   ```python
   models.UniqueConstraint(
       fields=["owner", "scenario_slug", "control"],
       condition=Q(status__in=["open", "in_progress"]),
       name="one_active_item_per_control_and_scenario",
       ...
   )
   ```

   Verified SQL (`sqlmigrate remediation 0001`):

   ```sql
   CREATE UNIQUE INDEX "one_active_item_per_control_and_scenario"
     ON "remediation_remediationitem" ("owner_id", "scenario_slug", "control_id")
     WHERE "status" IN ('open', 'in_progress');
   ```

### 1.3 JSON columns

`SimulationRun.enabled_controls`, `input_snapshot`, `result`, `PropagationEvent.controls_applied`
and `AuditEvent.metadata` are `JSONField`s (stored as text in SQLite, queried with Django's JSON
lookups, e.g. `metadata__attempted_username__iexact` in `accounts/throttling.py`). The snapshot
carries `snapshot_version` (currently 2; version 2 added `control_assumptions`), and the code
comment in `simulation/services.py` says readers "must tolerate its absence in version-1
snapshots". Schema changes inside JSON are therefore versioned by hand, not by migrations.

### 1.4 Append-only audit table

`AuditEvent` refuses changes in Python: `save()` raises when `pk` is set, `delete()` raises,
and its manager is `AppendOnlyQuerySet`, whose `update()` and `delete()` raise. The only
sanctioned delete is `purge_audit_events`, which calls the private `_purge()`. SQLite itself
would accept an `UPDATE`: there are no triggers (`docs/engineering-assessment.md` H3,
"database-level triggers remain future work").

### 1.5 Backup and restore

`python manage.py backup_db [--output DIR] [--keep N]` (`core/management/commands/backup_db.py`)
uses SQLite's online backup API (`sqlite3.Connection.backup`), runs `PRAGMA integrity_check` on
the copy, deletes it if the check fails, and keeps the newest N copies (default 14) named
`codeguard-<UTC timestamp>.sqlite3`. Restore is a documented manual procedure in
`docs/deployment.md` §7. Status: the command is covered by
`test_backup_db_writes_a_verified_copy_and_rotates`; a restore drill is not automated.

## Part 2 — Django migrations, taught with CodeGuard's files

### 2.1 What a migration is

A migration is a Python file that describes one step in the evolution of the database schema
(and optionally data). Django keeps, for each app, an ordered chain of these files in
`<app>/migrations/`. The database records which ones have been applied in the table
`django_migrations` (columns `app`, `name`, `applied`).

**Why they exist.** Models change over time. Migrations let every copy of the database (a
developer laptop, a CI database, production) be brought to the same schema by running the same
files in the same order, and they preserve existing rows while doing it.

**How it works, in four steps:**

1. You change `models.py`.
2. `python manage.py makemigrations` compares the models with the state described by the
   existing migration files and writes a new file containing the difference as *operations*.
3. `python manage.py migrate` applies every unapplied migration, in dependency order, inside a
   transaction (SQLite supports transactional DDL), and inserts a row into `django_migrations`.
4. Commit the migration file together with the model change.

Django never inspects the live database to decide what to generate: it replays the migration
files in memory to build the "project state". That is why a missing migration file is a bug and
why CI runs `makemigrations --check --dry-run`.

### 2.2 Anatomy of a migration: `accounts/migrations/0001_initial.py`

```python
class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('admin', 'Administrator'), ('analyst', 'Analyst'), ('viewer', 'Viewer')], default='viewer', max_length=16)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.CheckConstraint(condition=models.Q(('role__in', ['admin', 'analyst', 'viewer'])), name='profile_role_valid')],
            },
        ),
    ]
```

* `initial = True` marks the first migration of the app.
* `dependencies` lists migrations that must run first. `swappable_dependency(settings.AUTH_USER_MODEL)`
  means "whatever migration creates the user model", so the `OneToOneField` has a table to
  reference.
* `operations` is an ordered list. `CreateModel` becomes `CREATE TABLE`; the `id` field is a
  `BigAutoField` because `DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`.
* The `CheckConstraint` becomes a SQL `CHECK` inside the table definition.
* The header comment (`# Generated by Django 5.2.18 on 2026-10-26 12:12`) shows the file was
  generated, not hand-written.

### 2.3 Dependencies across apps

The full graph (from the `dependencies` lists):

```
auth (Django) ─┬─> accounts.0001 → 0002 → 0003 → 0004 → 0005 → 0006
               ├─> audit.0001 → 0002 → 0003 → 0004
               ├─> threats.0001 → 0002 → 0003 ─────────────┐
               │        └──> simulation.0001 ──────────────┤
               └───────────────────────────────────────────┴─> remediation.0001
```

`simulation.0001` depends on `threats.0001` because `SimulationRun.scenario` is a foreign key to
`ThreatScenario`. `remediation.0001` depends on `simulation.0001` (for `source_run`) and on
`threats.0003` (the latest `SecurityControl` state when it was generated). Django orders
everything topologically, so `migrate` on an empty database works without you choosing an order.
**Verified:** a fresh `migrate` applied all files, ending with
`simulation.0001_initial… OK`, `remediation.0001_initial… OK`, `sessions.0001_initial… OK`.

### 2.4 Adding fields: `accounts/migrations/0002_preferences.py` and `threats/0003`

`0002_preferences` contains three operations in one file: two `AddField` operations on
`profile` (`job_title`, `team`, both `blank=True`) and a `CreateModel` for `UserPreference`.
Because both new `CharField`s default to empty strings, existing profile rows get `''` and no
question is asked.

`threats/migrations/0003_control_assumptions.py` adds two `TextField(blank=True)` columns to
`SecurityControl`. `sqlmigrate` shows what SQLite actually does:

```sql
-- Add field effectiveness_basis to securitycontrol
CREATE TABLE "new__threats_securitycontrol" (... "effectiveness_basis" text NOT NULL, ...
    CONSTRAINT "control_effectiveness_range" CHECK ("effectiveness" <= 100));
INSERT INTO "new__threats_securitycontrol" (..., "effectiveness_basis")
    SELECT ..., '' FROM "threats_securitycontrol";
DROP TABLE "threats_securitycontrol";
ALTER TABLE "new__threats_securitycontrol" RENAME TO "threats_securitycontrol";
```

**Lesson:** SQLite's `ALTER TABLE` is limited, so Django rebuilds the table: create a new one,
copy the rows (filling `''` for the new column), drop the old one, rename. This happens twice,
once per added field. It is safe inside a transaction but costs time proportional to table size,
which is negligible for 14 control rows.

### 2.5 Changing only `choices`: the surface migrations and the audit actions

`0003_surface_preference` added `surface` with choices `paper`, `neutral`. `0004_pearl_surface`
and `0005_sage_surface` each widened the choices with an `AlterField`. Verified:

```
$ python manage.py sqlmigrate accounts 0004
BEGIN;
-- Alter field surface on userpreference
-- (no-op)
COMMIT;
```

Choices are enforced by Django forms and `full_clean()`, not by the database, so the SQL is a
no-op. The migration still has to exist because the choices are part of the field definition
in the project state. The same pattern drives `audit.0002`–`0004`: each new `AuditAction` member
required an `AlterField` on `AuditEvent.action` (25 choices today), and each one is a SQL no-op.

**Lesson:** forgetting such a migration does not break the database, but `makemigrations
--check` (run by `tests/test_integration.py::test_migrations_are_consistent_with_models`,
GitHub Actions and the Jenkinsfile) fails the build.

### 2.6 A data migration: `accounts/migrations/0006_retire_neutral_surface.py`

When the "Neutral" surface was retired, existing users could still hold that value. The
migration moves them to the default before narrowing the choices:

```python
def move_neutral_to_paper(apps, schema_editor):
    """The Neutral surface was retired; its users get the default, Paper."""
    UserPreference = apps.get_model("accounts", "UserPreference")
    UserPreference.objects.filter(surface="neutral").update(surface="paper")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_sage_surface")]

    operations = [
        # Data first, so no row is left holding a value the new choices reject.
        # Reversing does nothing: there is no record of who had chosen Neutral.
        migrations.RunPython(move_neutral_to_paper, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userpreference",
            name="surface",
            field=models.CharField(choices=[("paper", "Paper"), ("pearl", "Pearl"), ("sage", "Sage")], default="paper", max_length=8),
        ),
    ]
```

Four rules this file demonstrates:

1. **Use `apps.get_model`, never import the model.** The function receives the *historical*
   model as it was at this point of the chain. Importing `accounts.models.UserPreference` would
   give today's model, which may have fields that do not exist yet when an old database is
   migrated.
2. **Order the operations.** Data first, then the schema/choice change.
3. **Decide what reversing means.** `RunPython.noop` makes the migration reversible without
   pretending to restore lost information. **Verified:** `migrate accounts 0005` printed
   `Unapplying accounts.0006_retire_neutral_surface... OK`, `showmigrations` then showed
   `[ ] 0006_retire_neutral_surface`, and `migrate accounts` re-applied it.
4. **Test the behaviour.** `accounts/tests/test_settings.py::test_retired_neutral_surface_is_rejected`
   checks that the old value is no longer accepted.

`sqlmigrate accounts 0006` prints `THIS OPERATION CANNOT BE WRITTEN AS SQL` for the
`RunPython` step: Python operations only exist at run time.

### 2.7 Changing a constraint's message: `threats/0002`

`0002_friendly_rule_constraint_messages` uses `AlterConstraint` (new in Django 5.2's
migration operations) to add `violation_error_message` to `unique_rule_per_edge` and
`rule_not_self_loop`. `sqlmigrate threats 0002` shows `(no-op)` twice: the message is used by
Django's model validation (`validate_constraints`), not by SQLite.

### 2.8 Commands you will use

| Task | Command (from the project root, venv active) |
|---|---|
| Apply everything | `python manage.py migrate` |
| See what is applied | `python manage.py showmigrations [app]` |
| Generate after a model change | `python manage.py makemigrations [app]` |
| Check nothing is missing (CI) | `python manage.py makemigrations --check --dry-run` |
| Show the SQL of one migration | `python manage.py sqlmigrate <app> <number>` |
| Roll an app back to a migration | `python manage.py migrate <app> <number>` (e.g. `accounts 0005`) |
| Roll an app back completely | `python manage.py migrate <app> zero` (drops its tables) |
| Write an empty migration for data | `python manage.py makemigrations <app> --empty --name <name>` |
| Use a throw-away database | set `DJANGO_DB_PATH` to another file first |

On Windows in this project, run them as `.venv\Scripts\python.exe manage.py …` because Python is
not on `PATH`.

### 2.9 A safe workflow for a model change (tutorial; not a real feature)

The following illustrates the steps with an invented field; CodeGuard does **not** have it.

1. Edit the model, e.g. add `review_note = models.TextField(blank=True)` to `RemediationItem`.
2. `python manage.py makemigrations remediation` → creates `0002_…py`. Read the file.
3. `python manage.py sqlmigrate remediation 0002` → expect a table rebuild on SQLite.
4. `DJANGO_DB_PATH=<scratch>.sqlite3 python manage.py migrate` → apply to a scratch copy (a
   restored backup is ideal).
5. `pytest` → the integration test fails if the migration is missing or stale.
6. Commit the model, the migration and any test together.
7. In production: `backup_db`, deploy, `migrate`, as in `docs/deployment.md` §9.

For a **non-nullable field without a default**, `makemigrations` asks for a one-off default for
existing rows; for a **rename**, it asks whether the field was renamed (answer yes, or it will
drop and re-add the column and lose data); for **removing a choice that rows still use**, write
a data migration first, exactly like `accounts.0006`.

### 2.10 Seed data is not a migration

Reference data (stages, controls, system scenarios) is loaded by
`python manage.py seed_codeguard`, not by a data migration. The command is idempotent
(`update_or_create` by key/slug), updates stages and controls on every run, leaves existing
system scenarios untouched unless `--reset-scenarios` is passed (which increments their
version), and creates development-only demo users with `--demo-users`, refusing unless
`DJANGO_DEBUG=true`. The Jenkinsfile runs it twice to prove idempotency, and
`TestSeedCommand::test_seed_is_idempotent` checks it. **Verified:** on the scratch database it
printed `Seeded 5 stages, 14 controls, 6 new system scenarios (6 total).`

Trade-off: a fresh database is empty until the command is run (the README Quick start includes
it), but administrators' edits to system scenarios are not overwritten by upgrades.

### 2.11 Pitfalls observed in this codebase

* Migration headers have two quoting styles (generated vs reformatted); harmless, and Ruff
  excludes migrations.
* `UserPreference` rows are created lazily (`preferences_for` uses `get_or_create`), so a
  migration that assumes every user has a preference row would be wrong.
* `Profile` rows are created by a `post_save` signal on the user model; users created before the
  `accounts` app existed (or by raw SQL) would have none, and `get_role` treats them as viewers.
* Before commit `eef6716`, `templates/reports/` was git-ignored, so a fresh clone migrated fine but
  failed at render time on the Reports pages: a version-control gap, not a migration problem.
