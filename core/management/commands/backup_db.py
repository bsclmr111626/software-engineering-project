"""Online, consistent backup of the SQLite database.

Uses SQLite's backup API, so it is safe while the application is running
(unlike copying the file, which can capture a half-written WAL). Each copy is
checked with ``PRAGMA integrity_check`` and old copies beyond ``--keep`` are
removed. Restore procedure: README "Backup and restore".
"""

import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Write a verified, timestamped copy of the SQLite database to --output (default: backups/)."

    def add_arguments(self, parser):
        parser.add_argument("--output", default=str(Path(settings.BASE_DIR) / "backups"))
        parser.add_argument("--keep", type=int, default=14, help="How many recent backups to keep (default 14).")

    def handle(self, *args, output, keep, **options):
        if connection.vendor != "sqlite":
            raise CommandError("backup_db supports SQLite only; use the database server's own backup tooling.")
        if keep < 1:
            raise CommandError("--keep must be at least 1.")
        source_path = Path(connection.settings_dict["NAME"])
        if not source_path.exists():
            raise CommandError(f"Database file not found: {source_path}")
        folder = Path(output)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"codeguard-{timezone.now():%Y%m%dT%H%M%S%fZ}.sqlite3"

        source = sqlite3.connect(source_path)
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
            status = copy.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            copy.close()
            source.close()
        if status != "ok":
            target.unlink(missing_ok=True)
            raise CommandError(f"Backup failed its integrity check ({status}); no backup was kept.")

        old = sorted(folder.glob("codeguard-*.sqlite3"))[:-keep]
        for path in old:
            path.unlink()
        self.stdout.write(
            self.style.SUCCESS(f"Backup written to {target} (integrity ok, {len(old)} old copy(ies) removed).")
        )
