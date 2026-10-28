"""CSV exports of simulation results.

Values that begin with a spreadsheet formula character are prefixed with a
single quote to prevent CSV/formula injection when opened in Excel etc.
"""

import csv

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def _writer(response):
    writer = csv.writer(response)
    return lambda row: writer.writerow([safe_cell(v) for v in row])


def write_run_csv(response, run):
    write = _writer(response)
    write(["CodeGuard simulation report"])
    write(["Run ID", str(run.id)])
    write(["Scenario", run.scenario_name])
    write(["Scenario version", run.scenario_version])
    write(["Executed (UTC)", run.created_at.strftime("%Y-%m-%d %H:%M:%S")])
    write(["Likelihood", run.likelihood, "Severity", run.severity, "Impact", run.impact, "Threshold", run.threshold])
    write(["Enabled controls", "; ".join(run.enabled_controls) or "none"])
    write(
        ["Inherent risk", run.inherent_risk, "Residual risk", run.residual_risk, "Classification", run.classification]
    )
    write([])
    write(
        [
            "Stage",
            "State",
            "State without controls",
            "Inherent likelihood",
            "Residual likelihood",
            "Preventive coverage",
            "Mitigating coverage",
            "Inherent risk",
            "Residual risk",
            "Classification",
            "Explanation",
        ]
    )
    for s in run.stage_results.all():
        write(
            [
                s.stage_name,
                s.state,
                s.inherent_state,
                s.inherent_likelihood,
                s.residual_likelihood,
                s.preventive_coverage,
                s.mitigating_coverage,
                s.inherent_risk,
                s.residual_risk,
                s.classification,
                s.explanation,
            ]
        )
    write([])
    write(
        [
            "Order",
            "Source",
            "Target",
            "Kind",
            "Base probability",
            "Coverage",
            "Effective probability",
            "Threshold",
            "Outcome",
            "Explanation",
        ]
    )
    for e in run.events.all():
        write(
            [
                e.order,
                e.source_name,
                e.target_name,
                e.kind,
                e.base_probability,
                e.control_coverage,
                e.effective_probability,
                e.threshold,
                e.outcome,
                e.explanation,
            ]
        )


def write_history_csv(response, runs):
    write = _writer(response)
    write(
        [
            "Run ID",
            "Executed (UTC)",
            "Owner",
            "Scenario",
            "Version",
            "Status",
            "Inherent risk",
            "Residual risk",
            "Classification",
            "Compromised stages",
            "Blocked attempts",
            "Enabled controls",
        ]
    )
    for run in runs:
        write(
            [
                str(run.id),
                run.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                run.user.get_username(),
                run.scenario_name,
                run.scenario_version,
                run.status,
                run.inherent_risk,
                run.residual_risk,
                run.classification,
                run.compromised_count,
                run.blocked_count,
                "; ".join(run.enabled_controls),
            ]
        )
