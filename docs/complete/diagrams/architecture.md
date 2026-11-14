# Diagram: system architecture

One Django process (any number of identical WSGI workers) serves server-rendered HTML, PNG
charts and CSV files from one SQLite file. Arrows show "calls / imports". The simulation engine
(`domain`, `engine`, `propagation`, `risk`, `recommendations`) imports nothing from Django.

```mermaid
flowchart TB
    browser["Browser<br/>HTML + Bootstrap, icons and fonts (all vendored)<br/>static/js/app.js"]

    subgraph django["Django 5.2 process — codeguard/settings.py, codeguard/urls.py"]
        mw["Middleware chain<br/>RequestId → Security → CSP → Session → Common<br/>→ CSRF → Auth → Messages → SessionEpoch → XFrame"]
        subgraph apps["Apps"]
            core["core<br/>landing, overview, supply chain,<br/>risk analysis, help, healthz,<br/>notifications, error pages"]
            accounts["accounts<br/>roles, registration, sign-in throttling,<br/>settings and preferences"]
            threats["threats<br/>stages, controls, scenarios, rules"]
            simulation["simulation<br/>views, services, charts, exports"]
            remediation["remediation<br/>plan items, verification"]
            audit["audit<br/>append-only events, log view"]
        end
        subgraph engine["Pure engine (no Django imports)"]
            domain["domain.py<br/>Stage, Edge, Control, SimulationInput"]
            eng["engine.py<br/>validate_input, simulate"]
            prop["propagation.py<br/>traverse, _path_likelihoods"]
            risk["risk.py<br/>raw_risk, residual_risk, classify"]
            rec["recommendations.py<br/>recommend, control_contributions"]
        end
        mpl["Matplotlib (Agg)<br/>simulation/charts.py"]
        svg["SVG geometry<br/>simulation/visual.py, core/svgcharts.py"]
        tpl["Templates<br/>templates/"]
    end

    db[("SQLite — db.sqlite3<br/>WAL, IMMEDIATE, foreign keys")]

    browser -->|HTTP| mw --> apps
    simulation --> eng
    eng --> prop --> risk
    eng --> domain
    rec --> eng
    simulation --> rec
    simulation --> mpl
    core --> mpl
    simulation --> svg
    core --> svg
    threats --> svg
    apps --> tpl
    apps -->|Django ORM| db
    accounts -->|record_event| audit
    threats -->|record_event| audit
    simulation -->|record_event| audit
    remediation -->|record_event| audit
    accounts -->|throttling reads| audit
```

Source files: `codeguard/settings.py` (`INSTALLED_APPS`, `MIDDLEWARE`, `DATABASES`),
`codeguard/urls.py`, `simulation/engine.py` (module docstring: "It never touches the database").
