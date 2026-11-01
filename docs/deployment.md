# Deploying and operating CodeGuard

This guide covers a single-server deployment: one Linux host, a WSGI server, a reverse proxy
terminating TLS, and SQLite on local disk. That matches the intended scale (one team, tens of
users). The database decision and the point at which to move to PostgreSQL are in
[architecture.md](architecture.md#database-sqlite-now-postgresql-when).

**What has and has not been verified.** The application settings, `check --deploy`, health check,
request IDs, JSON logging, backup and retention commands are covered by automated tests and were
run on the development machine. The reverse-proxy and process-manager snippets below are standard
examples for orientation; they have **not** been run against a real server as part of this
project.

## 1. Prerequisites

- Python 3.12, a dedicated system user, and a directory such as `/srv/codeguard`.
- A WSGI server. CodeGuard does not pin one because the choice depends on the host:
  `gunicorn` on Linux, `waitress` on Windows. Install it into the same virtual environment.
- A reverse proxy (nginx, Caddy or a cloud load balancer) that terminates HTTPS.

## 2. Configuration

Copy `.env.example` to `.env` (readable only by the service user) or set the variables in the
process manager. Production values:

| Variable | Production value | Why |
|---|---|---|
| `DJANGO_DEBUG` | `false` | Turns on secure cookies, HSTS and the HTTPS redirect, and requires a secret key. |
| `DJANGO_SECRET_KEY` | 50+ random characters | Signs sessions and tokens. Never commit it. |
| `DJANGO_ALLOWED_HOSTS` | your host name | Rejects requests for other hosts. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://your.host` | Needed when the proxy changes the origin. |
| `DJANGO_BEHIND_PROXY` | `true` | Trusts `X-Forwarded-Proto` from the proxy so HTTPS is detected. Only set it when a proxy always overwrites that header. |
| `DJANGO_HSTS_SECONDS` | `31536000` once HTTPS is stable | Start with `3600` while testing. |
| `DJANGO_DB_PATH` | `/srv/codeguard/data/codeguard.sqlite3` | Keep the database outside the code directory. |
| `CODEGUARD_REGISTRATION` | `domain` or `closed` | `open` lets anyone who can reach the site create an Analyst account; `check --deploy` warns about it (`codeguard.W001`). |
| `CODEGUARD_REGISTRATION_DOMAINS` | e.g. `example.edu` | Required with `domain`. |
| `CODEGUARD_LOG_FORMAT` | `json` | One JSON object per line for log collectors. |
| `CODEGUARD_LOGIN_MAX_FAILURES`, `CODEGUARD_LOGIN_IP_MAX_FAILURES`, `CODEGUARD_LOGIN_LOCKOUT_MINUTES` | defaults 5, 20, 15 | Sign-in throttling. Raise the IP limit if many users share one NAT address. |
| `DJANGO_EMAIL_BACKEND`, `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`, `DJANGO_EMAIL_USE_TLS`, `DJANGO_DEFAULT_FROM_EMAIL` | the SMTP backend and your mail server | Password-reset email. The default prints emails to the console. |

## 3. First deployment

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt gunicorn
python manage.py check --deploy          # must show no errors; read every warning
python manage.py migrate
python manage.py seed_codeguard          # stages, control catalog, teaching scenarios
python manage.py createsuperuser         # first administrator
python manage.py collectstatic --noinput # writes staticfiles/ for the proxy to serve
```

With `CODEGUARD_REGISTRATION=closed`, administrators create further accounts in the Django
admin (`/admin/`) and assign roles on **Users and roles**.

## 4. Running the application (example, not tested here)

```ini
# /etc/systemd/system/codeguard.service
[Service]
User=codeguard
WorkingDirectory=/srv/codeguard/app
EnvironmentFile=/srv/codeguard/.env
ExecStart=/srv/codeguard/app/.venv/bin/gunicorn codeguard.wsgi:application --bind 127.0.0.1:8000 --workers 3
Restart=on-failure
```

Several workers are safe with the SQLite settings in `codeguard/settings.py` (WAL and immediate
transactions); all workers must run on the same host as the database file.

## 5. Reverse proxy (example, not tested here)

```nginx
server {
    listen 443 ssl;
    server_name codeguard.example.edu;
    # ssl_certificate / ssl_certificate_key ...

    location /static/ { alias /srv/codeguard/app/staticfiles/; }
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;   # correlates proxy and app logs
    }
    location /admin/ {                               # optional: restrict the Django admin
        allow 10.0.0.0/8; deny all;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 6. Health checks and monitoring

- `GET /healthz/` returns `200 {"status": "ok", "database": "ok"}`, or `503` if the database
  cannot be queried. It reveals nothing else and needs no session. Point the load balancer or
  uptime monitor at it.
- Every response has an `X-Request-ID` header, and every log line includes the same ID. When a
  user reports a problem, ask for the time and, if possible, that header.
- Alert on: health check failures, `ERROR` log lines, bursts of `login_throttled` audit events
  (password guessing), and `simulation_failed` events.

## 7. Backup and restore

Take backups with the built-in command, which is safe while the application is running:

```bash
python manage.py backup_db --output /srv/codeguard/backups --keep 14   # e.g. nightly from cron
```

Each copy is checked with `PRAGMA integrity_check`; old copies beyond `--keep` are removed. Copy
the backup directory off the host as well; a backup on the same disk does not survive disk loss.

To restore:

1. Stop the application (`systemctl stop codeguard`).
2. Move the current database and any `-wal`/`-shm` files aside (do not delete them yet).
3. Copy the chosen backup to `DJANGO_DB_PATH`.
4. Run `python manage.py migrate` (a no-op unless the backup predates a code upgrade).
5. Start the application and check `/healthz/` and a few reports.

Test a restore on a spare machine periodically; an untested backup is not a backup.

## 8. Data retention

- **Audit events** grow without bound. Keep them as long as your policy requires, then run, for
  example monthly: `python manage.py purge_audit_events --days 365`. It refuses less than 30
  days, supports `--dry-run`, and records its own run in the audit log.
- **Simulation runs** and **remediation items** belong to users and are deleted with the user.
  There is no automatic expiry, because reports are the product's record of past assessments.
- Audit events store usernames, object identifiers and client IP addresses. Include them in your
  privacy notice and access requests.

## 9. Upgrades

1. `python manage.py backup_db`.
2. Deploy the new code and install `requirements.txt`.
3. `python manage.py check --deploy` and `python manage.py migrate`.
4. `python manage.py seed_codeguard` (updates the control catalog; leaves edited scenarios alone).
5. `python manage.py collectstatic --noinput`, then restart the service.
