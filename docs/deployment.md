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
| `CODEGUARD_CLIENT_IP_HEADER` | e.g. `X-Real-IP` | The header your proxy overwrites with the visitor's address. Needed behind a proxy so sign-in limits and audit records use the real address; leave unset otherwise. |
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
- `.github/workflows/uptime.yml` requests `/healthz/` and the home page every 30 minutes from
  GitHub Actions and fails the run (GitHub then emails the workflow's last editor) when either
  is down. Set the repository variable `CODEGUARD_URL` to check a different address. GitHub
  pauses scheduled workflows after 60 days without repository activity, so an external
  monitor is still worth adding.
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
- **Closed accounts.** A user can close their own account (Settings > Privacy and data). It is
  inactive at once and deleted, with everything it owns, by `python manage.py
  purge_closed_accounts` once `CODEGUARD_ACCOUNT_DELETION_DAYS` (default 14) have passed.
  `scripts/release.sh` runs the command at every release; schedule it as well if releases are
  rare. Reactivating the user in Settings > Users before then cancels the deletion.
- **Audit protection.** After every `migrate`, SQLite triggers are (re)installed that refuse
  edits to audit rows and deletion of rows younger than 30 days (`audit/integrity.py`). They stop
  mistakes and casual tampering; someone with full database access can still remove them.
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

`scripts/release.sh` runs these steps in order on a server checkout and adds two safeguards:
it rehearses the migrations on a copy of the fresh backup before touching the real database,
and it checks `/healthz/` afterwards. It stops at the first failure and prints the commit and
backup to roll back to. Set `CODEGUARD_WSGI_FILE` (touched to reload the app) and
`CODEGUARD_URL` (for the health check). It was run end to end on a scratch clone on Windows
Git Bash; it has not yet been run on the live server.

## 10. PythonAnywhere (free plan): the live instance

CodeGuard runs at <https://codeguard.pythonanywhere.com> on PythonAnywhere's free Beginner plan (deployed
2026-11-12). PythonAnywhere supplies the WSGI server, the TLS proxy and static-file serving, so
sections 4 and 5 do not apply there. This is how it was set up; it was run, not just written.

**1. Code and packages** (Bash console). Paste one line at a time: the console can prefix a
multi-line paste with `^[[200~`, which breaks the first command.

```bash
cd ~ && git clone https://github.com/20Jojo/codeguard.git
python3.12 -m venv ~/.virtualenvs/codeguard
source ~/.virtualenvs/codeguard/bin/activate
pip install --no-cache-dir -r ~/codeguard/requirements.txt   # no cache: 512 MB disk quota
```

**2. Configuration, database, static files.** In `~/codeguard`, create `.env` (the settings
load it) with `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS=codeguard.pythonanywhere.com`,
`DJANGO_CSRF_TRUSTED_ORIGINS=https://codeguard.pythonanywhere.com`, `DJANGO_BEHIND_PROXY=true`,
`CODEGUARD_REGISTRATION=closed` and `CODEGUARD_DEFAULT_ROLE=analyst`, then append a secret key
generated on the server so it is never displayed:

```bash
python -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(50))" >> .env
chmod 600 .env
python manage.py migrate
python manage.py seed_codeguard            # no --demo-users: refused when DEBUG is off
python manage.py collectstatic --noinput
python manage.py check --deploy           # expect 0 errors; W005 and W021 only
python manage.py createsuperuser          # becomes a CodeGuard admin
```

**3. Web app** (Web tab → Add a new web app → Manual configuration → Python 3.12). Source
code `/home/codeguard/codeguard`; virtualenv `/home/codeguard/.virtualenvs/codeguard`; static
files URL `/static/` → `/home/codeguard/codeguard/staticfiles`; Force HTTPS on. Replace the
whole WSGI file (`/var/www/codeguard_pythonanywhere_com_wsgi.py`) with:

```python
import os
import sys

path = "/home/codeguard/codeguard"
if path not in sys.path:
    sys.path.insert(0, path)

os.environ["DJANGO_SETTINGS_MODULE"] = "codeguard.settings"

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
```

Then click Reload.

**Upgrades.** Push to `20Jojo/codeguard`, then in a Bash console with the virtualenv active:

```bash
cd ~/codeguard
export CODEGUARD_WSGI_FILE=/var/www/codeguard_pythonanywhere_com_wsgi.py
export CODEGUARD_URL=https://codeguard.pythonanywhere.com
bash scripts/release.sh
```

The first release that contains the script still needs one manual `git pull` to fetch it.

**Backups.** Every release takes one. Between releases, run `python manage.py backup_db` from
a scheduled task if the plan offers one, otherwise by hand weekly, and download the newest
file from `~/codeguard/backups/` (Files tab) so a copy exists off the server.

**Visitor addresses.** Sign in and open Settings > Sessions. If the address shown is not your
own public address, the server is seeing the proxy: add the header the host documents for the
client address (PythonAnywhere: `X-Real-IP`) as `CODEGUARD_CLIENT_IP_HEADER` in `.env`,
reload, and check again. Until then the per-IP sign-in limit is shared by all visitors.

**Email (Brevo).** PythonAnywhere's free plan blocks SMTP but allows `api.brevo.com`, so
CodeGuard sends account email over Brevo's HTTPS API (`core/email.py`). Brevo's free plan needs
no card. Without a domain of your own, mail goes out from one verified address and is more
likely to land in spam; SPF, DKIM and DMARC records need a custom domain.

1. Create a Brevo account, then under Senders verify the address mail should come from.
2. Create an API key (SMTP & API > API keys).
3. Add to `~/codeguard/.env`, then Reload:

   ```
   DJANGO_EMAIL_BACKEND=core.email.BrevoEmailBackend
   BREVO_API_KEY=<the key>
   DJANGO_DEFAULT_FROM_EMAIL=CodeGuard <the verified address>
   CODEGUARD_CONTACT_EMAIL=<where people should write>
   CODEGUARD_ADMIN_EMAILS=<where server errors should go>
   ```

4. In a console: `python manage.py send_test_email you@example.com`. It prints Brevo's reason
   if the message is refused.

Until email works, invitations still work: the Users page shows each invitation link once, to
copy and send by hand.

**Access.** Keep `CODEGUARD_REGISTRATION=closed` and invite people from Settings > Users.
Self-registration with email confirmation exists, but every account on an instance can read
every shared report, so open sign-up waits for workspaces
(`docs/PRODUCT_AND_ENGINEERING_AUDIT.md`, section 7).

**Free-plan limits.** One web app, 512 MB of disk, 100 console CPU-seconds a day (consoles slow
down rather than stop), outbound internet from code limited to allow-listed sites, no custom
domain. The web app must be extended ("Run until 3 months from today" on the Web tab) or it is
disabled. Brevo's free plan has a daily sending limit; check its current value in your Brevo account.
