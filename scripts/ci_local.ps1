# Run the same quality gates as the Jenkinsfile on a Windows developer machine.
# Usage (from the project root, with the virtual environment created):
#   powershell -ExecutionPolicy Bypass -File scripts\ci_local.ps1
$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"
$env:DJANGO_SETTINGS_MODULE = "codeguard.test_settings"

function Step($name, [scriptblock]$block) {
    Write-Host "==> $name" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) { throw "Step failed: $name" }
}

Step "Ruff lint" { & $py -m ruff check . }
Step "Ruff format check" { & $py -m ruff format --check . }
Step "Django system checks" { & $py manage.py check }
Step "Migration consistency" { & $py manage.py makemigrations --check --dry-run }
Step "Tests with coverage" { & $py -m pytest --cov --cov-report=term }
Step "Core coverage gate (85%)" {
    & $py -m coverage report --include=simulation/engine.py,simulation/risk.py,simulation/propagation.py,simulation/recommendations.py --fail-under=85
}
Step "Deployment configuration check" { & $py scripts/ci_deploy_check.py }
Step "Dependency audit (exit 2 = advisory service unreachable)" { & $py scripts/ci_dependency_audit.py }
Write-Host "All quality gates passed." -ForegroundColor Green
