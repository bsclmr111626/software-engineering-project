from django.core.management.base import BaseCommand
from django.db import transaction

from threats.models import (
    ControlCategory,
    Level,
    PropagationRule,
    ScenarioControl,
    ScenarioStatus,
    SecurityControl,
    SupplyChainStage,
    ThreatScenario,
    Visibility,
)

STAGES = [
    {
        "key": "external_input",
        "name": "External Input",
        "position": 6,
        "description": "Untrusted data entering an application through users, APIs, requests, or external integrations.",
        "assets": "HTTP requests, API parameters, form data, uploaded content, external messages.",
        "icon": "box-arrow-in-down",
        "weight": 4,
    },
    {
        "key": "application",
        "name": "Application Processing",
        "position": 7,
        "description": "Application logic that validates, transforms, and processes incoming data.",
        "assets": "Application code, input validation, business logic, request handlers.",
        "icon": "code-square",
        "weight": 5,
    },
    {
        "key": "operating_system",
        "name": "Operating System",
        "position": 8,
        "description": "Operating-system processes and execution privileges available to the application.",
        "assets": "Shell commands, processes, system accounts, environment variables.",
        "icon": "terminal",
        "weight": 5,
    },
    {
        "key": "database",
        "name": "Database",
        "position": 9,
        "description": "Database operations influenced by application-controlled input.",
        "assets": "SQL queries, database accounts, records, database services.",
        "icon": "database",
        "weight": 5,
    },
    {
        "key": "file_system",
        "name": "File System",
        "position": 10,
        "description": "Application access to local files, directories, and storage resources.",
        "assets": "Application files, configuration files, user documents, directories.",
        "icon": "folder",
        "weight": 4,
    },
    {
        "key": "deserialization",
        "name": "Deserialization",
        "position": 11,
        "description": "Conversion of serialized external data into application objects.",
        "assets": "Serialized objects, JSON or other payloads, object constructors, type metadata.",
        "icon": "braces",
        "weight": 4,
    },
]


CONTROLS = [
    {
        "slug": "app-input-validation",
        "name": "Application Input Validation",
        "description": "Validate untrusted input using explicit formats, types, length limits, and allowlists.",
        "category": ControlCategory.PREVENTIVE,
        "stages": ["external_input", "application"],
        "effectiveness": 65,
        "effort": Level.MEDIUM,
        "priority": Level.HIGH,
        "addresses": "Untrusted input reaching sensitive application operations.",
        "effectiveness_basis": "Illustrative reduction in risk when validation is consistently applied at application boundaries.",
        "limitations": "Validation alone does not replace context-specific parameterization, safe APIs, or authorization.",
    },
    {
        "slug": "safe-command-execution",
        "name": "Safe Operating-System Command Execution",
        "description": "Avoid shell interpretation, use fixed executable paths and argument lists, and validate permitted arguments.",
        "category": ControlCategory.PREVENTIVE,
        "stages": ["application", "operating_system"],
        "effectiveness": 85,
        "effort": Level.MEDIUM,
        "priority": Level.HIGH,
        "addresses": "Command injection through user-controlled operating-system command arguments.",
        "effectiveness_basis": "Illustrative effectiveness of avoiding shell execution and constraining command arguments.",
        "limitations": "Unsafe executable options, malicious programs, and other execution paths may remain.",
    },
    {
        "slug": "command-execution-least-privilege",
        "name": "Least-Privilege Process Execution",
        "description": "Run application processes using restricted operating-system accounts and minimal permissions.",
        "category": ControlCategory.PREVENTIVE,
        "stages": ["operating_system"],
        "effectiveness": 70,
        "effort": Level.MEDIUM,
        "priority": Level.HIGH,
        "addresses": "The impact of unauthorized command execution.",
        "effectiveness_basis": "Illustrative reduction in the privileges available to a compromised process.",
        "limitations": "Does not prevent command injection or protect resources accessible to the restricted account.",
    },
    {
        "slug": "command-execution-monitoring",
        "name": "Process Execution Monitoring",
        "description": "Monitor unexpected child processes, suspicious command arguments, and abnormal process behaviour.",
        "category": ControlCategory.DETECTIVE,
        "stages": ["operating_system"],
        "effectiveness": 55,
        "effort": Level.MEDIUM,
        "priority": Level.MEDIUM,
        "addresses": "Detection of suspicious operating-system command execution.",
        "effectiveness_basis": "Illustrative detection coverage for monitored process activity.",
        "limitations": "Detection depends on telemetry, alert quality, and response time.",
    },
    {
        "slug": "parameterized-sql-queries",
        "name": "Parameterized Database Queries",
        "description": "Use parameterized queries or ORM query APIs instead of constructing SQL using untrusted input.",
        "category": ControlCategory.PREVENTIVE,
        "stages": ["application", "database"],
        "effectiveness": 90,
        "effort": Level.MEDIUM,
        "priority": Level.HIGH,
        "addresses": "SQL injection caused by untrusted input being interpreted as SQL syntax.",
        "effectiveness_basis": "Illustrative effectiveness of separating SQL instructions from query parameters.",
        "limitations": "Unsafe dynamic SQL identifiers, stored procedures, and other query construction paths require separate review.",
    },
    {
        "slug": "database-least-privilege",
        "name": "Database Account Least Privilege",
        "description": "Give application database accounts only the permissions needed for their assigned functions.",
        "category": ControlCategory.PREVENTIVE,
        "stages": ["database"],
        "effectiveness": 70,
        "effort": Level.MEDIUM,
        "priority": Level.HIGH,
        "addresses": "The impact of unauthorized database queries.",
        "effectiveness_basis": "Illustrative reduction in database operations available to a compromised application.",
        "limitations": "Does not prevent SQL injection or prevent unauthorized access to data within granted permissions.",
    },
    {
        "slug": "database-query-monitoring",
        "name": "Database Query Monitoring",
        "description": "Monitor abnormal query patterns, unexpected access, and suspicious database activity.",
        "category": ControlCategory.DETECTIVE,
        "stages": ["database"],
        "effectiveness": 55,
        "effort": Level.MEDIUM,
        "priority": Level.MEDIUM,
        "addresses": "Detection of suspicious database queries and access patterns.",
        "effectiveness_basis": "Illustrative detection coverage for monitored database activity.",
        "limitations": "Legitimate queries may appear anomalous, and detection does not prevent unauthorized queries.",
    },
    {
        "slug": "canonical-file-path-validation",
        "name": "Canonical File Path Validation",
        "description": "Canonicalize paths and enforce that resolved paths remain within explicitly permitted directories.",
        "category": ControlCategory.PREVENTIVE,
        "stages": ["application", "file_system"],
        "effectiveness": 85,
        "effort": Level.MEDIUM,
        "priority": Level.HIGH,
        "addresses": "Path traversal through user-controlled file and directory paths.",
        "effectiveness_basis": "Illustrative effectiveness of canonical path resolution and directory boundary checks.",
        "limitations": "Symbolic links, race conditions, and inconsistent path handling require additional safeguards.",
    },
    {
        "slug": "restricted-file-access",
        "name": "Restricted Application File Access",
        "description": "Restrict application filesystem permissions to the directories and files required for operation.",
        "category": ControlCategory.PREVENTIVE,
        "stages": ["file_system"],
        "effectiveness": 70,
        "effort": Level.MEDIUM,
        "priority": Level.HIGH,
        "addresses": "Unauthorized file access and the impact of path traversal.",
        "effectiveness_basis": "Illustrative reduction in the files and directories accessible to the application.",
        "limitations": "Files within permitted directories may still be exposed.",
    },
    {
        "slug": "file-access-monitoring",
        "name": "File Access Monitoring",
        "description": "Monitor unusual application file access, sensitive file reads, and unexpected directory traversal.",
        "category": ControlCategory.DETECTIVE,
        "stages": ["file_system"],
        "effectiveness": 55,
        "effort": Level.MEDIUM,
        "priority": Level.MEDIUM,
        "addresses": "Detection of suspicious filesystem access.",
        "effectiveness_basis": "Illustrative detection coverage for monitored filesystem activity.",
        "limitations": "Detection requires suitable audit telemetry and does not prevent unauthorized file access.",
    },
    {
        "slug": "safe-deserialization",
        "name": "Safe Deserialization",
        "description": "Avoid deserializing untrusted data using unsafe object reconstruction mechanisms. Prefer safe data formats and parsers.",
        "category": ControlCategory.PREVENTIVE,
        "stages": ["external_input", "deserialization"],
        "effectiveness": 90,
        "effort": Level.MEDIUM,
        "priority": Level.HIGH,
        "addresses": "Unsafe object construction from untrusted serialized input.",
        "effectiveness_basis": "Illustrative effectiveness of avoiding unsafe object deserialization.",
        "limitations": "Safe formats can still contain malicious or unexpected values requiring validation.",
    },
    {
        "slug": "deserialization-schema-validation",
        "name": "Deserialized Data Validation",
        "description": "Validate deserialized data against strict schemas, expected types, and permitted object structures.",
        "category": ControlCategory.PREVENTIVE,
        "stages": ["deserialization", "application"],
        "effectiveness": 75,
        "effort": Level.MEDIUM,
        "priority": Level.HIGH,
        "addresses": "Unexpected object structures and values entering application processing.",
        "effectiveness_basis": "Illustrative effectiveness of strict schema and type validation.",
        "limitations": "Schema validation does not make an inherently unsafe deserialization mechanism safe.",
    },
    {
        "slug": "deserialization-monitoring",
        "name": "Deserialization Activity Monitoring",
        "description": "Monitor unusual serialized payloads, unexpected object types, and suspicious deserialization errors.",
        "category": ControlCategory.DETECTIVE,
        "stages": ["deserialization"],
        "effectiveness": 50,
        "effort": Level.MEDIUM,
        "priority": Level.MEDIUM,
        "addresses": "Detection of suspicious deserialization activity.",
        "effectiveness_basis": "Illustrative detection coverage for monitored deserialization operations.",
        "limitations": "Detection depends on logging and may not identify every malicious payload.",
    },
]


SCENARIOS = [
    {
        "slug": "application-command-injection",
        "name": "Application Command Injection",
        "description": (
            "A hypothetical attack in which untrusted application input reaches an "
            "operating-system command execution operation without adequate separation "
            "between data and executable instructions."
        ),
        "entry": "external_input",
        "likelihood": 65,
        "severity": 5,
        "impact": 5,
        "business_impact": "Potential unauthorized command execution, application compromise, data exposure, and service disruption.",
        "asset_categories": "Application, operating system, credentials, sensitive data",
        "assumptions": "An input path reaches a command execution operation. This is a modelled possibility, not proof of successful exploitation.",
        "preventive_measures": "Avoid shell execution, use argument arrays, validate permitted arguments, and apply least privilege.",
        "detective_measures": "Monitor process creation, command arguments, and unusual child processes.",
        "rules": [
            ("external_input", "application", 90, "Untrusted input reaches application processing."),
            (
                "application",
                "operating_system",
                85,
                "Application processing reaches an operating-system command execution path.",
            ),
        ],
        "controls": [
            "app-input-validation",
            "safe-command-execution",
            "command-execution-least-privilege",
            "command-execution-monitoring",
        ],
    },
    {
        "slug": "application-sql-injection",
        "name": "Application SQL Injection",
        "description": (
            "A hypothetical attack in which untrusted application input influences "
            "SQL query construction or execution and changes the intended database operation."
        ),
        "entry": "external_input",
        "likelihood": 65,
        "severity": 5,
        "impact": 5,
        "business_impact": "Potential unauthorized data access, data modification, data deletion, and regulatory exposure.",
        "asset_categories": "Application, database, customer records, credentials",
        "assumptions": "An input path influences a database query. A static analysis finding alone does not establish exploitability.",
        "preventive_measures": "Use parameterized queries, ORM APIs, strict input validation, and restricted database accounts.",
        "detective_measures": "Monitor abnormal database query patterns and unexpected data access.",
        "rules": [
            ("external_input", "application", 90, "Untrusted input reaches application processing."),
            ("application", "database", 85, "Application processing influences database query execution."),
        ],
        "controls": [
            "app-input-validation",
            "parameterized-sql-queries",
            "database-least-privilege",
            "database-query-monitoring",
        ],
    },
    {
        "slug": "application-path-traversal",
        "name": "Application Path Traversal",
        "description": (
            "A hypothetical attack in which untrusted input manipulates a file path "
            "to access files outside the application's intended directory boundaries."
        ),
        "entry": "external_input",
        "likelihood": 60,
        "severity": 4,
        "impact": 4,
        "business_impact": "Potential disclosure, modification, or deletion of sensitive files and application configuration.",
        "asset_categories": "Application, file system, configuration files, user documents",
        "assumptions": "An input path influences filesystem access. Successful traversal depends on path handling and filesystem permissions.",
        "preventive_measures": "Canonicalize resolved paths, enforce directory boundaries, and restrict filesystem permissions.",
        "detective_measures": "Monitor unusual file access and attempts to access sensitive directories.",
        "rules": [
            ("external_input", "application", 85, "Untrusted input reaches application path handling."),
            ("application", "file_system", 85, "Application processing influences filesystem access."),
        ],
        "controls": [
            "app-input-validation",
            "canonical-file-path-validation",
            "restricted-file-access",
            "file-access-monitoring",
        ],
    },
    {
        "slug": "application-insecure-deserialization",
        "name": "Application Insecure Deserialization",
        "description": (
            "A hypothetical attack in which untrusted serialized data is processed "
            "using unsafe object reconstruction or insufficiently constrained deserialization."
        ),
        "entry": "external_input",
        "likelihood": 55,
        "severity": 5,
        "impact": 5,
        "business_impact": "Potential unauthorized object construction, application compromise, privilege abuse, or denial of service.",
        "asset_categories": "Application, serialized data, object constructors, operating system",
        "assumptions": "An external payload reaches a deserialization operation. The actual impact depends on the format, runtime, available classes, and execution path.",
        "preventive_measures": "Avoid unsafe deserialization, use safe formats, validate schemas, and restrict process privileges.",
        "detective_measures": "Monitor unexpected object types, suspicious payloads, and deserialization errors.",
        "rules": [
            ("external_input", "deserialization", 90, "Untrusted serialized data reaches deserialization."),
            ("deserialization", "application", 80, "Deserialized objects enter application processing."),
            ("application", "operating_system", 60, "Application processing may reach privileged runtime operations."),
        ],
        "controls": [
            "safe-deserialization",
            "deserialization-schema-validation",
            "command-execution-least-privilege",
            "deserialization-monitoring",
        ],
    },
]


class Command(BaseCommand):
    help = "Seed the application-security stages, controls, and threat scenarios."

    @transaction.atomic
    def handle(self, *args, **options):
        stages = {}

        for data in STAGES:
            values = data.copy()
            key = values.pop("key")

            stage, _ = SupplyChainStage.objects.update_or_create(
                key=key,
                defaults={
                    **values,
                    "graph_type": SupplyChainStage.GraphType.APPLICATION,
                },
            )
            stages[key] = stage

        controls = {}

        for data in CONTROLS:
            values = data.copy()
            slug = values.pop("slug")
            stage_keys = values.pop("stages")

            control, _ = SecurityControl.objects.update_or_create(
                slug=slug,
                defaults=values,
            )
            control.stages.set([stages[key] for key in stage_keys])
            controls[slug] = control

        for data in SCENARIOS:
            values = data.copy()
            slug = values.pop("slug")
            entry_key = values.pop("entry")
            rules = values.pop("rules")
            control_slugs = values.pop("controls")

            scenario, _ = ThreatScenario.objects.update_or_create(
                slug=slug,
                defaults={
                    **values,
                    "initial_stage": stages[entry_key],
                    "visibility": Visibility.SHARED,
                    "status": ScenarioStatus.ACTIVE,
                    "is_system": True,
                    "owner": None,
                },
            )

            # Keep the seeded propagation graph deterministic on reruns.
            scenario.rules.all().delete()

            PropagationRule.objects.bulk_create(
                [
                    PropagationRule(
                        scenario=scenario,
                        source=stages[source],
                        target=stages[target],
                        probability=probability,
                        rationale=rationale,
                    )
                    for source, target, probability, rationale in rules
                ]
            )

            # Remove obsolete links before assigning the current catalogue.
            ScenarioControl.objects.filter(scenario=scenario).exclude(control__slug__in=control_slugs).delete()

            for control_slug in control_slugs:
                ScenarioControl.objects.update_or_create(
                    scenario=scenario,
                    control=controls[control_slug],
                    defaults={"note": "Relevant mitigation for this application-security scenario."},
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Application-security catalogue seeded successfully: "
                f"{len(STAGES)} stages, {len(CONTROLS)} controls, "
                f"{len(SCENARIOS)} scenarios."
            )
        )
