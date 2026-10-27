// CodeGuard CI pipeline (Declarative).
//
// Agent prerequisites: Python 3.12+ on PATH (as `python3` on Linux/macOS or
// `python` on Windows) and Git. Plugins: Pipeline, Git, JUnit, and optionally
// "Coverage" (or Cobertura) for coverage charts. No deployment credentials
// are needed: this pipeline only builds, checks and tests.

pipeline {
    agent any

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
    }

    environment {
        // CI uses the dedicated test settings and an isolated, temporary database.
        DJANGO_SETTINGS_MODULE = 'codeguard.test_settings'
        DJANGO_DB_PATH = "${WORKSPACE}/reports/ci-db.sqlite3"
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
        PYTHONDONTWRITEBYTECODE = '1'
        CORE_COVERAGE_MIN = '85'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Environment setup') {
            steps {
                script {
                    env.PY = isUnix() ? '.venv/bin/python' : '.venv\\Scripts\\python.exe'
                }
                runCmd(isUnix() ? 'python3 -m venv .venv' : 'python -m venv .venv')
                runCmd("${env.PY} -m pip install --upgrade pip")
                runCmd("${env.PY} -m pip install -r requirements-dev.txt")
                runCmd("${env.PY} --version")
            }
        }

        stage('Static checks') {
            steps {
                runCmd("${env.PY} -m ruff check .")
                runCmd("${env.PY} -m ruff format --check .")
                runCmd("${env.PY} manage.py check")
            }
        }

        stage('Database preparation') {
            steps {
                script {
                    if (isUnix()) { sh 'mkdir -p reports' } else { bat 'if not exist reports mkdir reports' }
                }
                // Fails if a model change has no migration.
                runCmd("${env.PY} manage.py makemigrations --check --dry-run")
                // Apply migrations and the seed twice to an isolated CI database (seed must be idempotent).
                runCmd("${env.PY} manage.py migrate --noinput")
                runCmd("${env.PY} manage.py seed_codeguard")
                runCmd("${env.PY} manage.py seed_codeguard")
            }
        }

        stage('Automated tests') {
            steps {
                runCmd("${env.PY} -m pytest --junitxml=reports/junit.xml --cov --cov-report=xml:reports/coverage.xml --cov-report=html:reports/htmlcov --cov-report=term")
            }
            post {
                always {
                    junit allowEmptyResults: false, testResults: 'reports/junit.xml'
                }
            }
        }

        stage('Coverage gate') {
            steps {
                // The core simulation and risk modules must stay above the threshold.
                runCmd("${env.PY} -m coverage report --include=simulation/engine.py,simulation/risk.py,simulation/propagation.py,simulation/recommendations.py --fail-under=${env.CORE_COVERAGE_MIN}")
            }
        }

        stage('Security checks') {
            steps {
                // Production-configuration check (manage.py check --deploy) using a random,
                // throwaway CI-only secret generated inside the script. Kept in Python so the
                // Groovy sandbox needs no script approvals.
                runCmd("${env.PY} scripts/ci_deploy_check.py")
                // Dependency vulnerability scan. Exit codes: 0 = no known vulnerabilities,
                // 1 = vulnerabilities found (fail), 2 = advisory service unreachable (unstable).
                script {
                    def status = runCmdStatus("${env.PY} scripts/ci_dependency_audit.py")
                    if (status == 1) {
                        error('pip-audit found known vulnerabilities in pinned dependencies. See reports/pip-audit.json.')
                    } else if (status == 2) {
                        unstable('pip-audit could not reach the vulnerability advisory service. Run it manually when online.')
                    } else if (status != 0) {
                        error("Dependency audit failed unexpectedly (exit code ${status}).")
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**', excludes: 'reports/ci-db.sqlite3', allowEmptyArchive: true, fingerprint: false
            script {
                // Optional: requires the "Coverage" plugin. Skipped cleanly if it is not installed.
                try {
                    recordCoverage(tools: [[parser: 'COBERTURA', pattern: 'reports/coverage.xml']])
                } catch (NoSuchMethodError ignored) {
                    echo 'Coverage plugin not installed; coverage.xml and htmlcov are still archived.'
                }
            }
        }
        failure {
            echo 'Build FAILED: see the first failing stage above (lint, migrations, tests, coverage gate or security checks).'
        }
        cleanup {
            // Remove the CI database and virtual environment; never touches developer data.
            script {
                if (isUnix()) { sh 'rm -rf .venv reports/ci-db.sqlite3' } else { bat 'if exist .venv rmdir /s /q .venv & if exist reports\\ci-db.sqlite3 del /q reports\\ci-db.sqlite3' }
            }
        }
    }
}

// Run a shell command on Unix agents or a batch command on Windows agents.
// Python and its tools accept forward slashes in arguments on Windows too.
def runCmd(String command) {
    if (isUnix()) {
        sh command
    } else {
        bat command
    }
}

// Same as runCmd, but returns the exit code instead of failing the stage.
def runCmdStatus(String command) {
    return isUnix() ? sh(returnStatus: true, script: command) : bat(returnStatus: true, script: command)
}
