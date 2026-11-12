# Diagram: CI/CD

Two pipeline definitions exist. **Neither deploys anything**: the live PythonAnywhere instance
is updated by hand (`git pull` on the server; see `docs/deployment.md` §10). Status, as far as
can be verified from this machine:

- `Jenkinsfile` — configured, **never executed on a Jenkins server**. Its commands were
  rehearsed by `scripts/rehearse_jenkinsfile.py` (README: SUCCESS on 2026-10-26).
- `.github/workflows/ci.yml` — configured and **passing**: run #7 on commit `8ca8b36`, 2026-11-10, 1 min 5 s. Runs #1–#6
  failed, first because `templates/reports/` was git-ignored (fixed in `eef6716`), then because
  Ruff's format check rewrote Python quoted in the new Markdown docs (fixed in `8ca8b36`).

## Jenkinsfile stages

```mermaid
flowchart LR
    A["Checkout<br/>checkout scm"] --> B["Environment setup<br/>venv, pip install -r requirements-dev.txt"]
    B --> C["Static checks<br/>ruff check, ruff format --check,<br/>manage.py check"]
    C --> D["Database preparation<br/>makemigrations --check,<br/>migrate, seed ×2 (idempotency)"]
    D --> E["Automated tests<br/>pytest --junitxml, --cov (xml + html)"]
    E --> F["Coverage gate<br/>core modules ≥ 85%"]
    F --> G["Security checks<br/>ci_deploy_check.py (check --deploy)<br/>ci_dependency_audit.py (pip-audit)"]
    G -->|exit 0| OK(["SUCCESS"])
    G -->|audit exit 2| UN(["UNSTABLE (advisory DB unreachable)"])
    G -->|audit exit 1| FAIL(["FAILURE"])
    E -. post always .-> J["junit reports/junit.xml"]
    G -. post always .-> AR["archiveArtifacts reports/**<br/>recordCoverage (if plugin present)"]
    AR -. cleanup .-> CL["delete .venv and CI database"]
```

## GitHub Actions job (`test`, ubuntu-latest, Python 3.12)

```mermaid
flowchart LR
    a["actions/checkout@v4"] --> b["actions/setup-python@v5<br/>3.12, pip cache"]
    b --> c["pip install -r requirements-dev.txt"]
    c --> d["Static checks: ruff check, ruff format --check,<br/>manage.py check, makemigrations --check"]
    d --> e["pytest --cov (term + xml)"]
    e --> f["Core coverage gate ≥ 85%"]
    f --> g["ci_deploy_check.py"]
    g --> h["ci_dependency_audit.py"]
```

Triggers: push to `main` and every pull request. Permissions: `contents: read`. Unlike Jenkins it
does not run `migrate`/`seed` separately (pytest builds its own database) and treats any non-zero
exit from the dependency audit, including the "unreachable" code 2, as a failure.

## Local equivalents

`scripts/ci_local.ps1` and `scripts/ci_local.sh` run the same gates on a developer machine;
`scripts/rehearse_jenkinsfile.py` clones the repository into a temporary directory and runs every
`runCmd` command extracted from the Jenkinsfile, in order.
