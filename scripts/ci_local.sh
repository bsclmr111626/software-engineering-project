#!/usr/bin/env bash
# Run the same quality gates as the Jenkinsfile on Linux/macOS.
# Usage: ./scripts/ci_local.sh   (from the project root, with .venv created)
set -euo pipefail
PY=.venv/bin/python
export DJANGO_SETTINGS_MODULE=codeguard.test_settings

echo "==> Ruff lint";              $PY -m ruff check .
echo "==> Ruff format check";      $PY -m ruff format --check .
echo "==> Django system checks";   $PY manage.py check
echo "==> Migration consistency";  $PY manage.py makemigrations --check --dry-run
echo "==> Tests with coverage";    $PY -m pytest --cov --cov-report=term
echo "==> Core coverage gate";     $PY -m coverage report --include=simulation/engine.py,simulation/risk.py,simulation/propagation.py,simulation/recommendations.py --fail-under=85
echo "==> Deploy config check";    $PY scripts/ci_deploy_check.py
echo "==> Dependency audit";       $PY scripts/ci_dependency_audit.py
echo "All quality gates passed."
