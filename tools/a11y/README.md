# Browser verification tools (optional)

These scripts drive a real headless Chrome through the DevTools protocol (Node 22+ built-in
WebSocket, no Puppeteer). They are **not needed to run CodeGuard**; they reproduce the
accessibility audit, keyboard checks and end-to-end journey recorded in `docs/test-plan.md`.

```powershell
# one-time
cd tools\a11y
npm install            # installs axe-core 4.10.2 only

# server in another terminal (from the project root, DEBUG=true, demo users seeded)
.\.venv\Scripts\python.exe manage.py runserver

npm run journey        # keyboard-driven journey; creates a user, 2 reports, 1 private scenario
npm run audit          # axe-core on every page at 1280px and 390px + focus + reflow
npm run errors         # axe-core on validation-error states
# Dark theme: set CODEGUARD_THEME=dark before audit/errors (PowerShell: $env:CODEGUARD_THEME='dark')
cd ..\..
.\.venv\Scripts\python.exe tools\authz_live.py    # live authorization matrix (uses journey.json)
```

Environment variables: `CODEGUARD_URL` (default `http://127.0.0.1:8000`), `CHROME_PATH`,
`CODEGUARD_ERROR_URL` (a second server with `DJANGO_DEBUG=false`, so the real 404 page is
audited; Django shows its own technical 404 page when DEBUG is true).

Run the journey before the audit on a fresh database: the audit discovers demo_analyst's reports
and private scenario, and skips those pages if none exist (it prints a note). Templates are cached
by Django; restart `runserver` after editing templates if it was started with `--noreload`.

Automated checks cannot replace testing with a real screen reader (NVDA, JAWS, VoiceOver).
