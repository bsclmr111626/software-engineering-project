# Diagram: request lifecycle

The order of the middleware is the order in `MIDDLEWARE` (`codeguard/settings.py`). On the way
out, responses pass back through the same middleware in reverse.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant RID as RequestIdMiddleware<br/>(core/observability.py)
    participant SEC as SecurityMiddleware
    participant CSP as ContentSecurityPolicyMiddleware<br/>(core/middleware.py)
    participant S as Session / Common / CSRF /<br/>Authentication / Messages
    participant EP as SessionEpochMiddleware<br/>(accounts/middleware.py)
    participant XF as XFrameOptionsMiddleware
    participant U as URL resolver<br/>(codeguard/urls.py)
    participant V as View (+ decorators)
    participant DB as SQLite

    B->>RID: GET /simulations/<uuid>/
    RID->>RID: reuse valid X-Request-ID or uuid4().hex
    RID->>SEC: forward (HTTPS redirect when DEBUG=false, except /healthz/)
    SEC->>CSP: forward
    CSP->>S: forward
    S->>S: load session, check CSRF on unsafe methods,<br/>attach request.user
    S->>EP: forward
    EP->>DB: preferences_for(user).session_epoch
    alt stored epoch differs (session revoked)
        EP-->>B: logout + redirect to /accounts/login/
    else matches (or first time: adopt it)
        EP->>XF: forward
        XF->>U: resolve path
        U->>V: detail(request, run_id)
        V->>V: @login_required (else redirect to login)
        V->>DB: get_accessible_run(user, run_id)<br/>owner OR (shared AND completed)
        alt not accessible
            V-->>B: Http404 → core.views.page_not_found
        else accessible
            V->>DB: stage_results, events, previous run, remediation items
            V-->>XF: render simulation/detail.html (context processors:<br/>role, shell → preferences, unread notifications)
        end
        XF-->>CSP: X-Frame-Options: DENY
        CSP-->>RID: Content-Security-Policy (not for /admin/), Permissions-Policy
        RID-->>B: X-Request-ID header
    end
```

Every log line written during the request carries the ID via `RequestIdFilter` (configured in
`LOGGING`).
