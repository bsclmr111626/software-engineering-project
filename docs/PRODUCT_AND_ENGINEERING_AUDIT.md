# CodeGuard product and engineering audit

**Date:** 2026-11-12 · **Scope:** the live site <https://codeguard.pythonanywhere.com/> (visited signed
out only) and the repository at commit `6986bab` (same tree as the deployed `20Jojo/codeguard`).

**How to read the evidence labels.** *Observed live* = seen on the deployed site today. *Read in
code* = confirmed in the named file. *Not checked* = needs access this audit did not have (a
signed-in session on the live site, the PythonAnywhere dashboard, or the server's `.env`).
Nothing was changed on the live site and no sign-in attempts were made against it.

Priorities: **P0** security, data loss or integrity · **P1** essential functionality and serious
defects · **P2** important UX, reliability and engineering work · **P3** enhancements.

---

## 1. Current product assessment

CodeGuard's core is sound. The simulation engine, risk model, threat library, reports, remediation
list and audit log work end to end, are covered by 337 passing tests (run today), and the public
methodology page matches the code. Security headers, CSRF, secure cookies, HTTPS redirect, friendly
error pages and a health check are all live.

What is missing is everything around the core that turns an application into a service other
people can use: **nobody can get an account without the owner creating one by hand, no email is
ever delivered, an address is never proven to belong to the person who typed it, there is no legal
or contact page, no backups run, and nothing tells the owner when the site breaks.** The product
is built for one trusted group on one instance; it has no concept of separate customers.

In short: a well-tested single-team tool that has been put on the public internet without the
account lifecycle, operations and tenancy a public service needs.

## 2. Existing feature inventory

| Area | Status | Evidence |
|---|---|---|
| Landing page, methodology page | Working | Observed live (`/`, `/help/` return 200) |
| Sign-in with username and password | Working | Observed live; `accounts/urls.py` |
| Sign-in throttling (5 per username, 20 per IP, 15 min) | Working on `/accounts/login/` only | `accounts/throttling.py`, `accounts/forms.py` |
| Self-registration form (username, email, password) | Built, **switched off** in production | `/accounts/register/` returns 403 live; `CODEGUARD_REGISTRATION=closed` |
| Password reset pages and tokens | Built, **delivers nothing** | Django's views in `accounts/urls.py`; console email backend |
| Password change, email change (asks current password) | Working | `accounts/views.py`, `accounts/settings_views.py` |
| Roles: viewer, analyst, administrator; server-side checks | Working | `accounts/permissions.py` |
| Settings: profile, appearance, typography, display, accessibility, notifications, privacy, security, sessions | Working | `accounts/settings_urls.py` |
| "Sign out other sessions" | Working | `accounts/middleware.py` |
| Personal data export (JSON) | Working | `settings_views.export_data` |
| User list and role change for administrators | Working, minimal | `accounts/views.py` |
| Threat library, custom scenarios, cloning, archiving | Working | `threats/` |
| Simulations, history, comparison, recommendations | Working | `simulation/` |
| Reports with CSV export, sharing | Working (CSV only) | `simulation/exports.py` |
| Remediation plan (status, note, due date) | Working, single-owner | `remediation/models.py` |
| Audit log, append-only in application code | Working | `audit/models.py` |
| In-app notification feed | Working (no email) | `core/notifications.py` |
| Health check, request IDs, JSON logging option | Working | `/healthz/` observed live |
| Backup and audit-retention commands | Built, **not scheduled** | `core/management/commands/backup_db.py` |
| CI on GitHub Actions (lint, tests, coverage gate, deploy check, dependency audit) | Working | `.github/workflows/ci.yml` |
| Jenkins pipeline | Configured, never run on a Jenkins server | `Jenkinsfile` |

## 3. Missing features

Not present anywhere in the code (read in code):

- Email verification, account activation, resend-verification.
- Invitations.
- Any way for an administrator to create, deactivate, reactivate or delete a user inside CodeGuard
  (only Django's `/admin/` can do it).
- Account deletion or deactivation by the user.
- Any email sent by CodeGuard itself (the only mail code is Django's built-in reset view).
- Notification of security events by email (password changed, email changed, new sign-in).
- Multi-factor authentication.
- Organizations or any tenant boundary.
- Privacy policy, terms of service, contact or support page (`/privacy/`, `/terms/` return 404 live).
- PDF report export.
- Remediation assignee, evidence and history.
- Error alerting, uptime monitoring, scheduled backups, a staging environment, automated deployment.
- `robots.txt`, `sitemap.xml`, social-preview metadata.

## 4. Partially implemented features

| Feature | What exists | What is missing |
|---|---|---|
| Registration | Form, role assignment, domain restriction, audit event | Verification, name fields, abuse protection, terms acknowledgement; it signs the user in immediately |
| Password reset | Pages, single-use 3-day tokens (Django default) | Delivery; rate limiting; audit event; the live page still says "In local development the email is printed to the server console" |
| Email change | Current-password check, uniqueness check, audit event | Proof that the new address works; notice to the old address |
| Email uniqueness | Checked in two forms | No database constraint, so `/admin/` or a race can create duplicates |
| User management | List, role change, self-demotion guard | Create, invite, suspend, search, detail, activity |
| Organization settings page | Read-only display of deployment settings | Nothing is editable; there is no organization |
| Audit "append-only" | Enforced in model, queryset and admin | Not enforced by the database; a shell or SQL can still edit rows. The landing page's wording should say "append-only in the application" |
| Reports | On-screen report, CSV | PDF, scheduled or emailed reports |
| Remediation | Status, due date, note, auto-verification from later runs | Assignment to another person, evidence, status history |
| Notifications | In-app feed | Email delivery |

## 5. Broken or unreliable workflows

1. **Getting access.** The landing page's only call to action is "Sign in", and the sign-in page
   says "Accounts are created by your administrator." There is no administrator contact and no
   in-product way for the administrator to create the account. A visitor has no next step.
2. **Forgot password.** The form accepts an address and shows success; nothing is sent. Anyone who
   forgets a password is locked out until the owner intervenes in `/admin/`.
3. **Mistyped email.** Because addresses are never verified, a typo at registration or email
   change makes the account unrecoverable by reset once email works.
4. **Leaving.** A user cannot close their account. If the owner deletes it, every simulation,
   scenario and remediation item they own is deleted with it (`on_delete=CASCADE`), including
   reports other people were reading.

## 6. Findings and recommendations

Complexity: **S** up to a day, **M** several days, **L** a week or more.

### P0

**P0-1 · No backups of the production database.**
*Evidence:* `backup_db` exists; `docs/deployment.md` says to run it nightly; nothing schedules it
(not checked on the server, but no schedule is documented). *Why it matters / who:* one bad
migration, mistaken delete or disk fault loses every user's work, permanently. *Fix:* run
`backup_db` on a schedule and copy the file off the server (download weekly at minimum); do a
restore drill once. *Complexity:* S. *Risk:* the free plan's scheduled-task allowance must be
confirmed in the dashboard; if there is none, back up as a step of every release plus a manual
weekly run. *Verify:* a restored copy opens and passes `PRAGMA integrity_check`.

**P0-2 · `/admin/` sign-in is not throttled.**
*Evidence (read in code):* throttling lives in `ThrottledAuthenticationForm`, used only by
`/accounts/login/`. `/admin/login/` (200 live) uses Django's own form, so the lockout never applies
there. Failures are still logged. *Why it matters:* the highest-privilege account can be guessed
at without limit. *Fix:* give the admin site the throttled form (`admin.site.login_form`), or
redirect `/admin/login/` to the main sign-in; consider moving `/admin/` to a non-default path.
*Complexity:* S. *Verify:* a test that six bad admin sign-ins are refused.

**P0-3 · Client IP behind PythonAnywhere's proxy is unknown.**
*Evidence:* `audit.services.client_ip` trusts only `REMOTE_ADDR`; `SECURITY.md` records the gap as
unchecked. *Why it matters:* if every request arrives from the proxy's address, the per-IP limit
is one shared bucket: 20 failed sign-ins from anyone lock **everyone** out for 15 minutes, and
every audit row carries a useless IP. *Fix:* look at the IP column of the live audit log; if it is
a proxy address, read the client address from the header PythonAnywhere sets, behind an explicit
setting. *Complexity:* S. *Verify:* audit rows show the visitor's address; throttling tests with
the header.

**P0-4 · No tenant boundary, so registration cannot simply be opened.**
*Evidence (read in code):* a "shared" scenario or report is visible to every account on the
instance (`is_shared`, `Visibility.SHARED`), and self-registered users become Analysts by default.
*Why it matters:* opening sign-up today would let any stranger read every shared report and write
content every other user sees. This is the reason registration is closed, and it is the real
blocker behind "sign-up is missing". *Fix:* see section 7. *Complexity:* L.

### P1

**P1-1 · No working email.** Console backend in production; no provider configured. Blocks reset,
verification, invitations and security notices. *Fix:* add a provider behind environment settings
(section 8), a `send_test_email` management command, and failure logging that never includes the
message body or tokens. *Complexity:* M. *Verify:* a real message received from the live server.

**P1-2 · No email verification.** *Fix:* new accounts start unverified and cannot sign in until
they open a signed, single-use, expiring link; resend is rate limited; responses never reveal
whether an address has an account. Email changes go through the same confirmation, with a notice
to the old address. Store `email_verified_at` on `Profile`. *Complexity:* M. *Verify:* tests for
expiry, reuse, tampering, resend limits and enumeration.

**P1-3 · No account creation path for administrators.** *Fix:* invitations: an administrator
enters an email and role; the invitee sets their own name and password from an emailed link that
expires and works once. Add suspend, reactivate, search and a user detail page. Administrators
never choose or see passwords. *Complexity:* M.

**P1-4 · Password reset is unusable and unprotected.** After P1-1: rate limit requests per address
and per IP, record an audit event, fix the misleading development sentence on the page, and email
the user when their password changes. *Complexity:* S.

**P1-5 · Email is not unique in the database, and sign-in is by username only.** *Fix:* a data
migration that checks for duplicates, then a case-insensitive unique constraint; allow sign-in
with either username or email. *Complexity:* M (it touches the built-in user table, so it needs a
rehearsal on a copy of the live data). 

**P1-6 · No privacy policy, terms or contact.** The site collects usernames, emails, names, job
titles, IP addresses and activity logs, and loads fonts from Google, which sends every visitor's
IP address to a third party. *Fix:* write plain-language pages that describe exactly this; host
the fonts locally; add a contact address. Kenya's Data Protection Act 2019 is the likely governing
law for this operator, and EU or UK visitors would bring GDPR into scope; that needs a qualified
opinion, not a claim in the footer. *Complexity:* S for pages and fonts.

**P1-7 · No account closure, and deletion destroys shared work.** *Fix:* self-service deactivation
with a grace period; decide what happens to shared reports (transfer to the organization or keep
with the author anonymized) before allowing deletion; change the cascades accordingly.
*Complexity:* M.

**P1-8 · Nobody is told when the site fails.** No `ADMINS`, no error reporting, no uptime check.
*Fix:* a free external monitor on `/healthz/`; error emails to the owner once P1-1 lands; a short
runbook. *Complexity:* S.

**P1-9 · Releases are manual and untested against real data.** `git pull` on the server, no
staging, no backup step enforced. *Fix:* a release checklist script: backup, pull, `check
--deploy`, `migrate`, `collectstatic`, reload, smoke test; rehearse every migration on a copy of
the production database first. *Complexity:* S.

### P2

- **Lockout as a weapon.** Five wrong guesses lock a known username for 15 minutes, repeatable
  forever. Add an emailed unlock link or progressive delays. (S)
- **Sign-up abuse protection.** Rate limits and a honeypot field before registration opens; no
  third-party CAPTCHA unless abuse appears. (S)
- **HSTS is one hour.** Raise in steps to a year once HTTPS is stable. Review warnings W005 and
  W021 again at that point. (S)
- **Security notices by email**, honoring the existing "account security" preference. (S)
- **Remediation as team work:** assignee, evidence link, status history, overdue view. (M)
- **PDF report export.** Matplotlib is already installed and can write PDF. (M)
- **First-run experience:** a guided first simulation and useful empty states. (M)
- **Audit integrity wording and hardening:** database triggers that refuse UPDATE and DELETE, or
  change the public claim. (S)
- **Dependency hygiene:** scheduled dependency audit, not only on push. (S)
- **`robots.txt`, sitemap, social metadata, a real 404 for `/favicon.ico`.** (S)

### P3

- Optional two-factor sign-in (TOTP) for administrators first.
- Scenario import and export; scenario version comparison.
- Scheduled report emails.
- PostgreSQL, only when concurrent writers or data size require it (section 9).
- Running Jenkins for real, or removing the Jenkinsfile's claims.

## 7. Organizations: the decision that shapes the rest

Three options were considered:

1. **Stay single-team, invitation only.** Smallest change. Fits a class or one company. Public
   visitors still cannot try the product.
2. **Open sign-up with no boundary.** Rejected: P0-4.
3. **Workspaces.** Every sign-up creates a private workspace; invitations add members with a
   workspace role; scenarios, runs, reports, remediation and audit rows belong to a workspace and
   "shared" means shared within it. Platform administration stays separate.

**Recommendation:** do option 1 now (it needs only email, verification and invitations, and gets
real people in within days), then option 3 as its own project before public sign-up is switched
on. Option 3 touches every query in `threats`, `simulation`, `remediation`, `audit` and
`core/analytics.py`; it needs a data migration that places all existing rows in one default
workspace, and a test suite that tries cross-workspace access on every URL. Doing it halfway is
worse than not doing it.

## 8. Email delivery on this host

Constraints, to be confirmed in the PythonAnywhere dashboard before choosing:

- Free accounts can only reach an allow-list of external sites, so the provider's API host must be
  on it; outbound SMTP is restricted. *Not checked.*
- The site has no domain of its own. SPF, DKIM and DMARC can only be set on a domain you control,
  so on `pythonanywhere.com` mail can only be sent from a provider's single verified sender
  address, with weaker deliverability. Proper authentication needs a custom domain, which costs
  money for the domain and for a PythonAnywhere plan that supports it.

Candidates with a free tier and an HTTPS API: Brevo, Mailgun, Resend, SendGrid, Postmark. The
choice is whichever is on the allow-list and allows single-sender verification; the code should
talk to it through one small backend class so the provider can be swapped.

## 9. Database and data integrity

SQLite in WAL mode with immediate transactions is appropriate for this load and this host; moving
to PostgreSQL now would add cost and operations for no user benefit. Revisit when there are
several worker processes writing at once or the file approaches the plan's disk limit (512 MB).
Integrity is otherwise good: check and unique constraints on roles, stages, rules, runs and
remediation items. The gaps are the email constraint (P1-5), the user-deletion cascades (P1-7)
and, later, workspace ownership on every table (section 7).

## 10. UX and design

Checked signed out only. The public pages are coherent, accessible (skip link, labelled forms,
strict CSP) and distinctive; the design system in `DESIGN.md` already rules out the generic
dark-and-neon look. Problems seen:

- No path from interest to access (section 5.1).
- The sign-in page promises "your organization's reports"; there is no organization.
- The footer's Account column offers only sign-in and reset.
- The reset page shows a developer note to the public.
- Sign-in asks for a username; most people expect their email.

The signed-in pages were **not reviewed live** in this audit. Before any redesign they need a
page-by-page walk with a test account on a staging copy, at phone and desktop widths, in both
themes.

## 11. Testing gaps

337 tests pass locally and in GitHub Actions. Not covered because the features do not exist:
verification, invitations, real email delivery, account closure, admin-site throttling,
cross-tenant access. Also absent: browser end-to-end tests of the main journeys, a migration
rehearsal against production-shaped data, and any load test.

## 12. Recommended order of work

| Phase | Contents | Outcome |
|---|---|---|
| 0. Protect what exists (days) | P0-1 backups, P0-2 admin throttling, P0-3 client IP, P1-8 uptime monitor, P1-9 release checklist | The live site can be changed safely |
| 1. Accounts people can actually get (1–2 weeks) | P1-1 email, P1-2 verification, P1-3 invitations and user management, P1-4 reset, P1-5 email uniqueness and email sign-in, P1-6 privacy, terms, contact, local fonts | Teammates are invited by email and can recover their own accounts |
| 2. Account lifecycle and trust (1 week) | P1-7 closure, lockout unlock, security notices, HSTS, audit hardening | Complete lifecycle |
| 3. Workspaces, then public sign-up (2–3 weeks) | Section 7 option 3, sign-up abuse protection, onboarding | Anyone can register safely |
| 4. Product depth | Remediation teamwork, PDF, first-run guide, 2FA | A fuller product |

Every phase ships through staging: backup, migration rehearsal on a copy of live data, full test
run, deploy, smoke test, with the previous commit and backup as the rollback.

## 13. Progress since the audit

Phase 0, in the repository but **not yet deployed to the live site**:

| Finding | State |
|---|---|
| P0-1 backups | `scripts/release.sh` backs up before every release. A schedule and an off-server copy still have to be set up on the host |
| P0-2 admin sign-in | Fixed in code and tested (`ThrottledAdminAuthenticationForm`) |
| P0-3 client IP | `CODEGUARD_CLIENT_IP_HEADER` added and tested. The live value still has to be checked and set |
| P1-8 monitoring | `.github/workflows/uptime.yml` checks the site every 30 minutes. Error emails wait for P1-1 |
| P1-9 releases | `scripts/release.sh`: backup, migration rehearsal on a copy, health check, rollback hint. Run on a scratch clone only |

Phase 0 was deployed on 2026-11-12; the client-IP header was then set on the live instance.

Phase 1, in the repository, **not yet deployed**:

| Finding | State |
|---|---|
| P1-1 email | `core.email.BrevoEmailBackend` (HTTPS, works on PythonAnywhere's free plan), plain-text templates in `templates/emails/`, `send_test_email`, deploy warning `codeguard.W002`, server errors emailed to `CODEGUARD_ADMIN_EMAILS`. Needs a Brevo account and key on the server |
| P1-2 verification | Self-registered accounts must confirm their address before signing in; email changes take effect only after the new address is confirmed and the old one is told. Signed, expiring, single-use links; confirmation needs a button press, so mail scanners cannot use the link. Resend with per-address and per-IP limits, same response for any address |
| P1-3 invitations and user management | Invitations with role, 7-day single-use links (only a hash stored), resend, revoke, link shown once to the admin. User search and filters, detail page with activity, suspend (ends sessions), reactivate, send reset link |
| P1-4 password reset | Per-address and per-IP limits, audit events, notice email after any password change, links expire after one hour, misleading page text fixed. A reset also confirms the address |
| P1-5 unique email, email sign-in | Case-insensitive unique index (migration stops and lists conflicts if data breaks it). Sign in with username or email; failed attempts by email count against the account |
| P1-6 legal pages | `/privacy/`, `/terms/`, `/contact/` describing actual behaviour, linked from the footer, sign-up and invitations. Fonts still load from Google, which the privacy notice says; hosting them locally is open |
| Sign-up | Name fields, terms acknowledgement, honeypot, five submissions per IP per hour, no disclosure of registered addresses (the owner is emailed instead). Still switched off on the live site (P0-4) |

Still open from Phase 1: local fonts. P1-7 (account closure) is Phase 2.

Phase 1 was deployed on 2026-11-14. Email delivery is **not configured on the live instance
yet**, so no flow that sends email has been proven there; invitations work only by copying the
link. The client-IP header is also still unset on the live instance (it reads `REMOTE_ADDR`).

Phase 2 and smaller items, in the repository, **not yet deployed**:

| Finding | State |
|---|---|
| P1-7 account closure | Self-service closure with password and confirmation; inactive at once, sessions ended, deleted with owned work after `CODEGUARD_ACCOUNT_DELETION_DAYS` by `purge_closed_accounts` (run at each release). Administrators can reopen before then. Superusers and the only administrator are refused. Shared reports are deleted with their owner; the confirmation page says how many. Transferring them to a workspace waits for Phase 3 |
| Audit integrity | SQLite triggers refuse edits to audit rows and deletion of rows younger than 30 days, reinstalled after every migrate. Guards against mistakes, not against someone with full database access |
| Unique email index | Reinstalled after every migrate as well, because SQLite table rebuilds drop it |
| Crawlers and previews | `/robots.txt` (public pages only), `/favicon.ico`, Open Graph metadata |
| Dependency audit | CI now also runs weekly |

Not done from Phase 2, because they need working email: an emailed unlock link for locked
accounts. Not done by choice: raising HSTS beyond one hour (set `DJANGO_HSTS_SECONDS` on the
server once HTTPS has been stable; it is hard to undo).

### Signed-in pages on the live site (checked 2026-11-14, read-only, administrator account)

Automated checks over 31 pages (every sidebar and settings page, plus the legal pages):

- All returned 200 in 0.4 to 0.9 seconds; no browser console errors.
- Each has exactly one main heading; no form control without a label, no image without
  alternative text, no duplicate element ids.
- At phone width (375 px) the five pages measured (overview, users, new simulation, audit table,
  privacy notice) do not scroll sideways. The settings navigation is wider than the screen there
  and scrolls within its own strip.
- A new account sees an empty state on seven pages (overview, results, risk analysis,
  remediation, reports, notifications, new simulation). Each explains itself, but nothing walks a
  first-time user through a first simulation; that onboarding gap (P2) stands.

Not done: a visual review (screenshots could not be taken in this session), the analyst and
viewer roles, pages that need data (a report, a comparison, a remediation item), dark theme, and
screen-reader testing.

## 14. What this audit could not verify

- Anything behind sign-in on the live site, including which accounts exist.
- The server's `.env`, scheduled tasks, disk usage and logs.
- PythonAnywhere's current free-plan allow-list, SMTP rules and scheduled-task allowance.
- `REMOTE_ADDR` behind the proxy (P0-3).
- Behaviour under load.
