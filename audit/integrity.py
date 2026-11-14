"""Database-level protection for records the application treats as fixed.

``AuditEvent`` refuses changes in Python (audit/models.py), but that does not
stop raw SQL or a shell. These SQLite triggers make the database refuse too:

* an audit row can never be edited, except that its ``actor_id`` may be set to
  NULL, which is what deleting a user does (the username stays on the row);
* an audit row can be deleted only once it is older than the shortest
  retention the purge command accepts (30 days).

They are installed after every ``migrate`` rather than by one migration,
because SQLite rebuilds a table when Django alters it, which silently drops
its triggers and expression indexes. The same hook re-creates the unique
email index from accounts migration 0008 for that reason.

Limits: anyone who can run SQL can also drop a trigger, so this guards
against mistakes and casual tampering, not a determined database owner. Other
database engines are left alone.
"""

from django.db import connection

MINIMUM_RETENTION_DAYS = 30

AUDIT_COLUMNS = [
    "id",
    "actor_username",
    "action",
    "object_type",
    "object_id",
    "object_repr",
    "metadata",
    "ip_address",
    "created_at",
]


def _statements():
    from django.contrib.auth import get_user_model

    from .models import AuditEvent

    audit = connection.ops.quote_name(AuditEvent._meta.db_table)
    users = connection.ops.quote_name(get_user_model()._meta.db_table)
    unchanged = " AND ".join(f"NEW.{c} IS OLD.{c}" for c in AUDIT_COLUMNS)
    return [
        f"""CREATE TRIGGER IF NOT EXISTS audit_event_no_update BEFORE UPDATE ON {audit}
            WHEN NOT (NEW.actor_id IS NULL AND {unchanged})
            BEGIN SELECT RAISE(ABORT, 'audit events are append-only'); END""",
        f"""CREATE TRIGGER IF NOT EXISTS audit_event_no_early_delete BEFORE DELETE ON {audit}
            WHEN OLD.created_at > datetime('now', '-{MINIMUM_RETENTION_DAYS} days')
            BEGIN SELECT RAISE(ABORT, 'audit events are kept for at least {MINIMUM_RETENTION_DAYS} days'); END""",
        f"CREATE UNIQUE INDEX IF NOT EXISTS accounts_user_email_ci_unique ON {users} (LOWER(email)) WHERE email <> ''",
    ]


def install(**kwargs):
    """post_migrate handler (audit/apps.py). Safe to run any number of times."""
    if connection.vendor != "sqlite":
        return
    existing = set(connection.introspection.table_names())
    with connection.cursor() as cursor:
        for statement in _statements():
            table = statement.split(" ON ", 1)[1].split()[0].strip('"')
            if table in existing:
                cursor.execute(statement)


def installed():
    """Names of the protections present, for the deployment check."""
    if connection.vendor != "sqlite":
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE name IN "
            "('audit_event_no_update', 'audit_event_no_early_delete', 'accounts_user_email_ci_unique')"
        )
        return {row[0] for row in cursor.fetchall()}
