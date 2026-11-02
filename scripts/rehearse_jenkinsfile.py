"""Rehearse the Jenkinsfile's commands on a clean checkout, without Jenkins.

This is NOT a Jenkins run: it does not parse Groovy or evaluate Declarative
syntax, plugins, `post` blocks or agent configuration. It extracts the shell
commands each stage passes to runCmd()/runCmdStatus(), in order, and runs
them in a fresh copy of the repository with a fresh virtual environment.
That proves the commands, files and dependencies the pipeline relies on work
from a clean checkout.

Usage:  python scripts/rehearse_jenkinsfile.py [workspace_dir]
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = shutil.which("git") or r"C:\Program Files\Git\cmd\git.exe"

STAGE = re.compile(r"stage\('([^']+)'\)")
VENV = re.compile(r"runCmd\(isUnix\(\) \? '([^']+)' : '([^']+)'\)")
CMD = re.compile(r"(runCmd|runCmdStatus)\(([\"'])(.+?)\2\)")
ENV_LINE = re.compile(r"^\s*([A-Z_]+) = ['\"](.*)['\"]\s*$")


def parse(jenkinsfile):
    """Return (environment dict, [(stage, kind, command), ...])."""
    env, steps, stage, in_env = {}, [], None, False
    for line in jenkinsfile.splitlines():
        if line.strip().startswith("environment {"):
            in_env = True
            continue
        if in_env:
            if line.strip() == "}":
                in_env = False
            elif match := ENV_LINE.match(line):
                env[match.group(1)] = match.group(2)
            continue
        if match := STAGE.search(line):
            stage = match.group(1)
            continue
        if line.strip().startswith("def runCmd"):
            break  # helper definitions, not pipeline steps
        if match := VENV.search(line):
            unix_cmd, windows_cmd = match.groups()
            steps.append((stage, "runCmd", windows_cmd if os.name == "nt" else unix_cmd))
        elif match := CMD.search(line):
            steps.append((stage, match.group(1), match.group(3)))
    return env, steps


def checkout(workspace):
    """Export tracked content (HEAD if it exists, else the staged index)."""
    has_head = subprocess.run([GIT, "rev-parse", "--verify", "HEAD"], cwd=ROOT, capture_output=True).returncode == 0  # noqa: S603
    if has_head:
        subprocess.run([GIT, "clone", "--quiet", str(ROOT), str(workspace)], check=True)  # noqa: S603
        return "git clone (HEAD)"
    subprocess.run([GIT, "checkout-index", "-a", f"--prefix={workspace}{os.sep}"], cwd=ROOT, check=True)  # noqa: S603
    return "git checkout-index (staged files; no commits yet)"


def main():
    workspace = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp(prefix="codeguard-ci-"))
    workspace.mkdir(parents=True, exist_ok=True)
    env_vars, steps = parse((ROOT / "Jenkinsfile").read_text(encoding="utf-8"))
    py = r".venv\Scripts\python.exe" if os.name == "nt" else ".venv/bin/python"

    env = os.environ.copy()
    for key, value in env_vars.items():
        env[key] = value.replace("${WORKSPACE}", str(workspace))
    # Agents need `python` on PATH; put this interpreter's directory first so the
    # venv-creation command resolves even where Python is not on PATH globally.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")

    print(f"Stage 'Checkout': {checkout(workspace)} -> {workspace}")
    (workspace / "reports").mkdir(exist_ok=True)
    unstable = False
    for stage, kind, command in steps:
        command = command.replace("${env.PY}", py)
        command = command.replace("${env.CORE_COVERAGE_MIN}", env_vars.get("CORE_COVERAGE_MIN", "85"))
        print(f"\n=== Stage '{stage}': {command}", flush=True)
        code = subprocess.run(command, cwd=workspace, env=env, shell=True).returncode  # noqa: S602 - commands come from our Jenkinsfile
        if kind == "runCmdStatus" and code == 2:
            print(">>> exit 2: pipeline would be marked UNSTABLE")
            unstable = True
        elif code != 0:
            print(f">>> FAILED with exit code {code}: the Jenkins build would fail in stage '{stage}'.")
            return code
    excluded = set(re.findall(r"excludes: '([^']+)'", (ROOT / "Jenkinsfile").read_text(encoding="utf-8")))
    reports = sorted(
        p.relative_to(workspace).as_posix()
        for p in (workspace / "reports").iterdir()
        if p.relative_to(workspace).as_posix() not in excluded
    )
    print(
        f"\nReports that Jenkins would archive: {', '.join(reports)} (excluded: {', '.join(sorted(excluded)) or 'none'})"
    )
    print("REHEARSAL RESULT:", "UNSTABLE" if unstable else "SUCCESS", "(commands only; not a Jenkins execution)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
