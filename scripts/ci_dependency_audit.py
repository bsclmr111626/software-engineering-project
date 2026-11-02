"""Dependency vulnerability scan for CI with unambiguous exit codes.

    0  no known vulnerabilities
    1  at least one known vulnerability (the build must fail)
    2  the scan could not complete, e.g. no network access (the build is unstable)

The JSON report is written to reports/pip-audit.json for archiving.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "reports" / "pip-audit.json"

NO_VULNERABILITIES, VULNERABLE, INCOMPLETE = 0, 1, 2
# Without network access pip-audit keeps retrying; cap it so an offline agent
# reports "incomplete" instead of hitting the pipeline's overall timeout.
SCAN_TIMEOUT_SECONDS = 180


def classify(report_text):
    """Return (exit_code, vulnerable package names) for a pip-audit JSON report."""
    try:
        data = json.loads(report_text)
    except (TypeError, ValueError):
        return INCOMPLETE, []
    dependencies = data.get("dependencies") if isinstance(data, dict) else data
    if not isinstance(dependencies, list):
        return INCOMPLETE, []
    vulnerable = [d.get("name", "?") for d in dependencies if isinstance(d, dict) and d.get("vulns")]
    return (VULNERABLE if vulnerable else NO_VULNERABILITIES), vulnerable


def main():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    command = [
        sys.executable, "-m", "pip_audit", "-r", str(ROOT / "requirements.txt"),
        "--format", "json", "--output", str(REPORT), "--timeout", "30",
    ]  # fmt: skip
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argument list, no shell
            command, capture_output=True, text=True, check=False, timeout=SCAN_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        print(f"pip-audit did not finish within {SCAN_TIMEOUT_SECONDS} s (no network access?).")
        return INCOMPLETE
    report_text = REPORT.read_text(encoding="utf-8") if REPORT.exists() else ""
    code, vulnerable = classify(report_text)
    if code == NO_VULNERABILITIES and completed.returncode != 0:
        code = INCOMPLETE  # pip-audit failed without producing a usable report
    if code == VULNERABLE:
        print(f"Known vulnerabilities found in: {', '.join(sorted(set(vulnerable)))}. See {REPORT}.")
    elif code == INCOMPLETE:
        print("pip-audit could not complete. Last output lines:")
        print("\n".join((completed.stderr or completed.stdout).strip().splitlines()[-5:]))
    else:
        print("No known vulnerabilities found.")
    return code


if __name__ == "__main__":
    sys.exit(main())
