"""Live authorization matrix against a running CodeGuard server.

Run tools/a11y/journey.mjs first: it creates a "victim" user with a private scenario and
two private reports and writes tools/a11y/journey.json. This script then attacks that data
as a second analyst, as demo_viewer and anonymously, over real HTTP with valid CSRF tokens,
and checks the database was not changed.

Usage:  python tools/authz_live.py   (server at CODEGUARD_URL, default http://127.0.0.1:8000)
"""

import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
BASE = os.environ.get("CODEGUARD_URL", "http://127.0.0.1:8000")
DB_PATH = os.environ.get("DJANGO_DB_PATH", str(ROOT / "db.sqlite3"))
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "CodeGuard-demo-2024")  # development-only demo accounts
TIMEOUT = 30

journey = json.loads((ROOT / "tools" / "a11y" / "journey.json").read_text(encoding="utf-8"))
SLUG = journey["privateScenario"]
RUN = journey["baseline"].strip("/").split("/")[1]
RUN2 = journey["improved"].strip("/").split("/")[1]
failures = 0
ITEM = None


def check(label, ok, detail=""):
    global failures
    failures += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'} {label}{(' -> ' + detail) if detail else ''}")


def _form_post(session, path, data):
    page = session.get(BASE + path, timeout=TIMEOUT)
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.text).group(1)
    return session.post(BASE + path, data={"csrfmiddlewaretoken": token, **data},
                        headers={"Referer": BASE + path}, allow_redirects=False, timeout=TIMEOUT)  # fmt: skip


def login(username, password):
    s = requests.Session()
    assert _form_post(s, "/accounts/login/", {"username": username, "password": password}).status_code == 302
    return s


def register(username, password):
    s = requests.Session()
    data = {"username": username, "email": f"{username}@example.com", "password1": password, "password2": password}
    assert _form_post(s, "/accounts/register/", data).status_code == 302, "registration failed"
    return s


def get(s, path):
    return s.get(BASE + path, allow_redirects=False, timeout=TIMEOUT)


def post(s, path, payload=None):
    s.get(f"{BASE}/overview/", timeout=TIMEOUT)  # make sure a csrftoken cookie exists
    body = {"csrfmiddlewaretoken": s.cookies.get("csrftoken"), **(payload or {})}
    return s.post(BASE + path, data=body, headers={"Referer": BASE + "/"}, allow_redirects=False, timeout=TIMEOUT)


def db_state():
    with sqlite3.connect(DB_PATH) as db:
        runs = db.execute("SELECT COUNT(*) FROM simulation_simulationrun").fetchone()[0]
        scenario = db.execute(
            "SELECT status, version, visibility FROM threats_threatscenario WHERE slug = ?", (SLUG,)
        ).fetchone()
        scenarios = db.execute("SELECT COUNT(*) FROM threats_threatscenario").fetchone()[0]
        items = db.execute("SELECT id, status, note FROM remediation_remediationitem ORDER BY id").fetchall()
    return runs, scenario, scenarios, items


def victim_remediation_item(victim):
    """Make sure the victim has a remediation item from their private report; return its id."""
    control = re.search(r'name="control" value="([^"]+)"', get(victim, f"/simulations/{RUN}/").text)
    if control:  # absent once every recommendation is already on the plan
        post(victim, "/remediation/track/", {"run": RUN, "control": control.group(1)})
    return re.search(r'href="/remediation/(\d+)/"', get(victim, "/remediation/?status=all").text).group(1)


def attack(name, s, is_viewer):
    print(f"\n--- {name} ---")
    for path in (f"/threats/{SLUG}/edit/", f"/threats/{SLUG}/delete/"):
        # Analysts get 404 (ownership), viewers 403 (role); identical for a non-existent slug either way.
        real, fake = get(s, path), get(s, path.replace(SLUG, "no-such-scenario-xyz"))
        check(f"GET {path}", real.status_code in (403, 404) and real.status_code == fake.status_code,
              f"{real.status_code} (non-existent slug: {fake.status_code})")  # fmt: skip
    for path in (f"/threats/{SLUG}/", f"/simulations/{RUN}/", f"/simulations/{RUN}/chart/stages.png",
                 f"/simulations/{RUN}/export.csv", f"/simulations/compare/?a={RUN}&b={RUN2}",
                 f"/simulations/compare/chart.png?a={RUN}&b={RUN2}", f"/simulations/{RUN}/paths/",
                 f"/simulations/{RUN}/controls/", f"/reports/{RUN}/"):  # fmt: skip
        r = get(s, path)
        check(f"GET {path}", r.status_code == 404, str(r.status_code))
    for path in (f"/threats/{SLUG}/archive/", f"/threats/{SLUG}/clone/", f"/threats/{SLUG}/delete/",
                 f"/simulations/{RUN}/share/"):  # fmt: skip
        r = post(s, path)
        check(f"POST {path}", r.status_code in (403, 404), str(r.status_code))
    r = get(s, f"/simulations/new/?rerun={RUN}")
    check("GET rerun of the victim's report", r.status_code in (403, 404), str(r.status_code))
    r = post(s, "/simulations/new/", {"scenario": SLUG, "likelihood": 50, "severity": 3, "impact": 3, "threshold": 50})
    if is_viewer:
        check("POST simulate the victim's private scenario", r.status_code == 403, str(r.status_code))
    else:
        check("POST simulate the victim's private scenario (forged)",
              r.status_code == 200 and "The simulation was not run." in r.text, f"{r.status_code}, visible rejection")  # fmt: skip
    listing = "".join(
        get(s, p).text
        for p in (
            "/threats/?status=all",
            "/reports/?scope=all",
            "/simulations/results/",
            "/simulations/",
            "/risk/",
            "/supply-chain/",
            "/overview/",
        )
    )
    check("private IDs absent from listings", SLUG not in listing and RUN not in listing)
    # Remediation plan items are private to their owner.
    r = get(s, f"/remediation/{ITEM}/")
    check(f"GET /remediation/{ITEM}/", r.status_code == 404, str(r.status_code))
    r = post(s, f"/remediation/{ITEM}/", {"status": "done", "note": "tampered"})
    check(f"POST /remediation/{ITEM}/ (change status)", r.status_code == 404, str(r.status_code))
    r = post(s, "/remediation/track/", {"run": RUN, "control": "mfa"})
    expected = 403 if is_viewer else 404
    check("POST /remediation/track/ on the victim's report", r.status_code == expected, str(r.status_code))
    check("victim's item absent from own plan", f"/remediation/{ITEM}/" not in get(s, "/remediation/?status=all").text)
    # Settings are always the signed-in user's own; administration pages are admin-only.
    for path in ("/settings/users/", "/settings/organization/"):
        r = get(s, path)
        check(f"GET {path}", r.status_code == 403, str(r.status_code))
    export = get(s, "/settings/privacy/export.json")
    check(
        "data export contains only own data",
        export.status_code == 200 and RUN not in export.text and SLUG not in export.text,
    )


def main():
    stamp = hex(int(time.time()))[2:]
    global ITEM
    victim = login(journey["user"], journey["password"])
    ITEM = victim_remediation_item(victim)
    before = db_state()
    attack("second analyst", register(f"intruder_{stamp}", f"Violet-Harbor-{stamp}-93"), is_viewer=False)
    attack("viewer (demo_viewer)", login("demo_viewer", DEMO_PASSWORD), is_viewer=True)

    print("\n--- anonymous ---")
    anon = requests.Session()
    for path in (f"/threats/{SLUG}/", f"/simulations/{RUN}/", f"/simulations/{RUN}/export.csv"):
        r = get(anon, path)
        check(
            f"GET {path}",
            r.status_code == 302 and "/accounts/login/" in r.headers.get("Location", ""),
            str(r.status_code),
        )
    r = anon.post(f"{BASE}/threats/{SLUG}/archive/", allow_redirects=False, timeout=TIMEOUT)
    check("POST archive without session/CSRF", r.status_code in (302, 403), str(r.status_code))

    print("\n--- victim's data ---")
    check("database unchanged by every attack", db_state() == before, f"{before} -> {db_state()}")
    check("owner still sees the private scenario", get(victim, f"/threats/{SLUG}/").status_code == 200)
    check("owner still sees the private report", get(victim, f"/simulations/{RUN}/").status_code == 200)
    check("owner still sees the remediation item", get(victim, f"/remediation/{ITEM}/").status_code == 200)

    print("\n--- explicit sharing is read-only ---")
    viewer = login("demo_viewer", DEMO_PASSWORD)
    check("owner shares the report", post(victim, f"/simulations/{RUN}/share/").status_code == 302)
    check("viewer can read the shared report", get(viewer, f"/simulations/{RUN}/").status_code == 200)
    check("viewer cannot change sharing", post(viewer, f"/simulations/{RUN}/share/").status_code == 403)
    check("unshared second report stays hidden", get(viewer, f"/simulations/{RUN2}/").status_code == 404)
    check("owner makes it private again", post(victim, f"/simulations/{RUN}/share/").status_code == 302)
    check("viewer loses access after unsharing", get(viewer, f"/simulations/{RUN}/").status_code == 404)

    print(f"\n{'ALL AUTHORIZATION CHECKS PASSED' if not failures else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
