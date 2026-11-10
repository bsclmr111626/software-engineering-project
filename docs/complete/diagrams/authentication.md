# Diagram: authentication and authorization

## Sign-in with throttling

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant LV as LoginView
    participant F as ThrottledAuthenticationForm<br/>(accounts/forms.py)
    participant T as throttling.is_locked<br/>(accounts/throttling.py)
    participant A as Django authenticate()
    participant SIG as accounts/signals.py
    participant AE as audit_auditevent

    B->>LV: POST /accounts/login/ (username, password, CSRF token)
    LV->>F: is_valid() → clean()
    F->>T: is_locked(username, REMOTE_ADDR)
    T->>AE: count login_failed for username since max(window start, last login)
    T->>AE: count login_failed for IP in window
    alt ≥ 5 per username or ≥ 20 per IP (defaults)
        F->>AE: record_event(login_throttled)
        F-->>B: "Too many failed sign-in attempts…" (password not checked)
    else not locked
        F->>A: authenticate(username, password)
        alt wrong credentials
            A->>SIG: user_login_failed
            SIG->>AE: record_event(login_failed, attempted_username) — never the password
            F-->>B: generic invalid-credentials error
        else correct
            LV->>SIG: user_logged_in
            SIG->>AE: record_event(login)
            SIG->>SIG: session[cg_session_epoch] = preferences.session_epoch<br/>session[cg_session_started], session[cg_session_agent]
            LV-->>B: redirect to /start/ → chosen start page
        end
    end
```

## Authorization decision for a protected view

```mermaid
flowchart TD
    req["Request reaches a view"] --> login{"Authenticated?<br/>(@login_required)"}
    login -- no --> redirect["302 → /accounts/login/?next=…"]
    login -- yes --> role{"Role check needed?<br/>analyst_required / admin_required"}
    role -- "role not allowed" --> f403["PermissionDenied → 403 page"]
    role -- "allowed or not needed" --> obj{"Object-level rule"}
    obj --> scen["Scenario: visible_scenarios()<br/>shared OR owner = user"]
    obj --> run["Run: accessible_runs()<br/>owner OR (shared AND completed)"]
    obj --> rem["Remediation: items_for()<br/>owner = user"]
    obj --> aud["Audit: admin → all events<br/>others → own events"]
    scen -- "not visible" --> f404["Http404 (existence not disclosed)"]
    run -- "not accessible" --> f404
    rem -- "not owner" --> f404
    scen -- "visible but can_edit / can_delete false" --> f403
    run -- "share toggle by non-owner" --> f403
    scen --> ok["Render / act"]
    run --> ok
    rem --> ok
    aud --> ok
```

Role resolution (`accounts/permissions.get_role`): anonymous → `None`; superuser → `admin`;
otherwise `user.profile.role`, or `viewer` when the profile row is missing.
