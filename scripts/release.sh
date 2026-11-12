#!/usr/bin/env bash
# Release the latest commit on a server checkout, safely.
#
# Run from the project folder with the virtual environment active:
#   bash scripts/release.sh
#
# Order: back up the database, pull, install, check the configuration, rehearse
# the migrations on a copy of the backup, migrate for real, collect static
# files, reload the web app, then check the health endpoint. It stops at the
# first failure and prints how to roll back.
#
# Optional environment variables:
#   CODEGUARD_WSGI_FILE  file to touch so the host reloads the app
#                        (PythonAnywhere: /var/www/<user>_pythonanywhere_com_wsgi.py)
#   CODEGUARD_URL        public base URL for the health check
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f manage.py ]; then
    echo "release: manage.py not found; run this from the CodeGuard checkout." >&2
    exit 1
fi
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "release: the checkout has local changes; commit or discard them first." >&2
    exit 1
fi

previous=$(git rev-parse HEAD)
backup=""

on_error() {
    echo >&2
    echo "release: FAILED. The site may be running a mix of old and new code." >&2
    echo "To roll back the code:      git reset --hard $previous" >&2
    if [ -n "$backup" ]; then
        echo "To restore the database:    see docs/deployment.md section 7; backup: $backup" >&2
    fi
    echo "Then collect static files and reload the web app." >&2
}
trap on_error ERR

echo "== 1/8 Back up the database"
python manage.py backup_db
backup=$(ls -1 backups/codeguard-*.sqlite3 | tail -n 1)

echo "== 2/8 Pull"
git pull --ff-only
if [ "$(git rev-parse HEAD)" = "$previous" ]; then
    echo "Already up to date; continuing so the checks still run."
fi

echo "== 3/8 Install requirements"
python -m pip install --quiet --no-cache-dir -r requirements.txt

echo "== 4/8 Check the deployment configuration"
python manage.py check --deploy --fail-level ERROR

echo "== 5/8 Rehearse migrations on a copy of the backup"
rehearsal=$(mktemp --suffix=.sqlite3)
cp "$backup" "$rehearsal"
DJANGO_DB_PATH="$rehearsal" python manage.py migrate --noinput
rm -f "$rehearsal" "$rehearsal-wal" "$rehearsal-shm"

echo "== 6/8 Migrate and seed reference data"
python manage.py migrate --noinput
python manage.py seed_codeguard

echo "== 7/8 Collect static files"
python manage.py collectstatic --noinput

echo "== 8/8 Reload and check"
if [ -n "${CODEGUARD_WSGI_FILE:-}" ]; then
    touch "$CODEGUARD_WSGI_FILE"
    echo "Reload requested ($CODEGUARD_WSGI_FILE)."
else
    echo "CODEGUARD_WSGI_FILE is not set: reload the web app yourself now."
fi
if [ -n "${CODEGUARD_URL:-}" ]; then
    sleep 5
    body=$(curl --silent --show-error --fail --max-time 30 "${CODEGUARD_URL%/}/healthz/")
    echo "Health: $body"
    case "$body" in
        *'"status": "ok"'*) ;;
        *) echo "release: health check did not report ok." >&2; false ;;
    esac
else
    echo "CODEGUARD_URL is not set: open /healthz/ and sign in to confirm."
fi

trap - ERR
echo "Released $(git rev-parse --short HEAD) (was $(git rev-parse --short "$previous")). Backup: $backup"
