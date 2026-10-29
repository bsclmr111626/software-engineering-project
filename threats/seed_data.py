"""Seed definitions for CodeGuard.

All scenarios are hypothetical teaching examples, not reports of real
incidents. Probabilities and effectiveness values are illustrative model
parameters chosen to make the propagation rules easy to reason about.
"""

STAGES = [
    {
        "key": "ide",
        "position": 1,
        "name": "IDE / Developer Environment",
        "icon": "laptop",
        "weight": 1,
        "description": "Developer workstations, local tooling and the accounts developers use to write and push code.",
        "assets": "Developer accounts, local source checkouts, SSH keys and access tokens, IDE extensions",
    },
    {
        "key": "vcs",
        "position": 2,
        "name": "Version Control",
        "icon": "git",
        "weight": 2,
        "description": "Source repositories that hold the authoritative code, history, branches and permissions.",
        "assets": "Repositories, branches, commits, pull requests, repository permissions",
    },
    {
        "key": "cicd",
        "position": 3,
        "name": "CI/CD Pipeline",
        "icon": "gear-wide-connected",
        "weight": 2,
        "description": "Automated build, test and release jobs that turn source code into deployable artifacts.",
        "assets": "Build jobs, runners, pipeline credentials, test results, release workflows",
    },
    {
        "key": "registry",
        "position": 4,
        "name": "Software Registry",
        "icon": "box-seam",
        "weight": 2,
        "description": "Package and artifact registries that store and distribute built software and dependencies.",
        "assets": "Published packages, container images, package versions, publishing credentials",
    },
    {
        "key": "production",
        "position": 5,
        "name": "Production",
        "icon": "hdd-network",
        "weight": 3,
        "description": "Running applications and services used by customers, plus the operational access to them.",
        "assets": "Deployed services, runtime configuration, production credentials, customer data",
    },
]

# (slug, name, category, stages, effectiveness, effort, priority, description, addresses)
CONTROLS = [
    (
        "mfa",
        "Multi-factor authentication",
        "preventive",
        ["ide", "vcs"],
        60,
        "low",
        "high",
        "Require a second factor for developer and repository accounts.",
        "Stolen or guessed passwords being enough to take over a developer or repository account.",
    ),
    (
        "least-privilege",
        "Least-privilege access",
        "preventive",
        ["vcs", "cicd", "registry", "production"],
        35,
        "medium",
        "high",
        "Grant each person and service only the permissions it needs, reviewed regularly.",
        "Over-privileged accounts that let one compromise reach several downstream stages.",
    ),
    (
        "protected-branches",
        "Protected branches and mandatory code review",
        "preventive",
        ["vcs"],
        50,
        "low",
        "high",
        "Block direct pushes to release branches and require independent review before merge.",
        "Unreviewed malicious changes entering the main branch.",
    ),
    (
        "signed-commits",
        "Signed commits / source verification",
        "preventive",
        ["vcs"],
        30,
        "medium",
        "medium",
        "Require cryptographically signed commits and verify author identity.",
        "Commits forged under another developer's identity.",
    ),
    (
        "isolated-builds",
        "Isolated build environments",
        "preventive",
        ["cicd"],
        45,
        "high",
        "medium",
        "Run every build in a fresh, isolated, ephemeral environment.",
        "Persistent build-runner tampering and cross-job contamination.",
    ),
    (
        "cicd-secrets",
        "Protected CI/CD secrets",
        "preventive",
        ["cicd"],
        50,
        "medium",
        "high",
        "Store pipeline secrets in a vault, scope them to jobs, and never expose them to untrusted code.",
        "Theft of pipeline credentials used to publish or deploy.",
    ),
    (
        "dependency-pinning",
        "Dependency pinning and integrity verification",
        "preventive",
        ["ide", "cicd"],
        50,
        "low",
        "high",
        "Pin dependency versions and verify hashes before installation.",
        "Malicious or substituted packages being pulled into builds and developer machines.",
    ),
    (
        "sca",
        "Software composition analysis",
        "detective",
        ["cicd", "registry"],
        40,
        "low",
        "medium",
        "Continuously scan dependencies and artifacts for known-malicious or vulnerable components.",
        "Compromised components going unnoticed after they enter the build.",
    ),
    (
        "artifact-signing",
        "Artifact signing and provenance verification",
        "preventive",
        ["registry", "production"],
        55,
        "high",
        "high",
        "Sign build outputs and verify signatures and provenance before publication and deployment.",
        "Tampered or unauthorized artifacts being published or deployed.",
    ),
    (
        "registry-access",
        "Registry access restrictions",
        "preventive",
        ["registry"],
        45,
        "medium",
        "medium",
        "Restrict who and what can publish to the registry; use short-lived publishing tokens.",
        "Unauthorized package publication with stolen registry credentials.",
    ),
    (
        "deploy-approvals",
        "Deployment approvals",
        "preventive",
        ["production"],
        40,
        "low",
        "medium",
        "Require a human approval gate before production deployments.",
        "Automated deployment of unexpected releases to production.",
    ),
    (
        "prod-secrets",
        "Production secret management",
        "preventive",
        ["production"],
        50,
        "medium",
        "high",
        "Keep production credentials in a managed secret store with rotation and scoped access.",
        "Long-lived exposed production credentials enabling direct access.",
    ),
    (
        "runtime-monitoring",
        "Runtime monitoring",
        "detective",
        ["production"],
        35,
        "medium",
        "medium",
        "Monitor production behavior and alert on anomalies.",
        "Malicious activity in production remaining undetected.",
    ),
    (
        "incident-response",
        "Incident response and recovery procedures",
        "recovery",
        ["ide", "vcs", "cicd", "registry", "production"],
        25,
        "medium",
        "medium",
        "Maintain tested runbooks for credential revocation, rollback and recovery.",
        "Slow containment and recovery after a compromise is detected.",
    ),
]

SCENARIOS = [
    {
        "slug": "compromised-developer-account",
        "name": "Compromised Developer Account",
        "initial_stage": "ide",
        "likelihood": 70,
        "severity": 4,
        "impact": 4,
        "description": "A developer account is assumed to be compromised, for example through a phished password. "
        "The simulation evaluates how weak authentication, excessive permissions, inadequate review and "
        "insufficient release verification affect downstream propagation.",
        "business_impact": "Unauthorized code may be merged and released to customers, damaging trust and requiring an emergency release.",
        "asset_categories": "Developer accounts, Source code, Build artifacts, Customer-facing services",
        "assumptions": "The attacker holds the developer's credentials and session. Developers can push to the main repository and trigger builds.",
        "preventive_measures": "Multi-factor authentication, least privilege, protected branches with mandatory review, signed commits.",
        "detective_measures": "Unusual-login alerts, commit-signature monitoring, incident response runbooks for credential revocation.",
        "rules": [
            ("ide", "vcs", 85, "Developer can push code to the repository"),
            ("ide", "cicd", 40, "Developer token can trigger pipeline jobs directly"),
            ("vcs", "cicd", 80, "Merged code is built automatically"),
            ("cicd", "registry", 70, "Pipeline publishes build outputs"),
            ("registry", "production", 65, "Published artifacts are deployed"),
        ],
        "controls": [
            "mfa",
            "least-privilege",
            "protected-branches",
            "signed-commits",
            "artifact-signing",
            "deploy-approvals",
            "incident-response",
        ],
    },
    {
        "slug": "compromised-vcs-account",
        "name": "Compromised Version Control Account",
        "initial_stage": "vcs",
        "likelihood": 60,
        "severity": 4,
        "impact": 4,
        "description": "An attacker is assumed to have unauthorized repository access. The simulation evaluates "
        "inadequate branch protection, insufficient review requirements and weak commit verification.",
        "business_impact": "Malicious changes in the source of truth can flow into every release and into developer machines.",
        "asset_categories": "Repositories, Source code, Developer environments, Releases",
        "assumptions": "The attacker can push branches and open or merge pull requests. Developers routinely pull the latest code.",
        "preventive_measures": "Protected branches, mandatory reviews, signed commits, least-privilege repository roles.",
        "detective_measures": "Audit-log review for permission changes, alerts on force-pushes, incident response.",
        "rules": [
            ("vcs", "ide", 30, "Developers pull tampered code locally (reverse path)"),
            ("vcs", "cicd", 85, "Repository changes trigger builds"),
            ("cicd", "registry", 75, "Pipeline publishes build outputs"),
            ("registry", "production", 70, "Published artifacts are deployed"),
        ],
        "controls": [
            "protected-branches",
            "signed-commits",
            "least-privilege",
            "mfa",
            "artifact-signing",
            "incident-response",
        ],
    },
    {
        "slug": "compromised-cicd-pipeline",
        "name": "Compromised CI/CD Pipeline",
        "initial_stage": "cicd",
        "likelihood": 55,
        "severity": 5,
        "impact": 5,
        "description": "A pipeline or its credentials are assumed to be compromised. The simulation evaluates the "
        "propagation of untrusted build outputs and unauthorized releases.",
        "business_impact": "Trusted release channels distribute attacker-controlled builds; production may be modified directly.",
        "asset_categories": "Build jobs, Pipeline credentials, Artifacts, Production deployments",
        "assumptions": "The pipeline holds publishing and deployment credentials, and has write access to the repository.",
        "preventive_measures": "Protected CI/CD secrets, isolated builds, artifact signing, deployment approvals.",
        "detective_measures": "Build provenance checks, software composition analysis, runtime monitoring, incident response.",
        "rules": [
            ("cicd", "vcs", 45, "Pipeline token can write back to the repository (reverse path)"),
            ("cicd", "registry", 90, "Pipeline publishes artifacts"),
            ("cicd", "production", 60, "Pipeline holds deployment credentials (bypass path)"),
            ("registry", "production", 80, "Published artifacts are deployed"),
        ],
        "controls": [
            "cicd-secrets",
            "isolated-builds",
            "artifact-signing",
            "deploy-approvals",
            "least-privilege",
            "sca",
            "incident-response",
        ],
    },
    {
        "slug": "malicious-dependency",
        "name": "Malicious Dependency",
        "initial_stage": "registry",
        "likelihood": 50,
        "severity": 4,
        "impact": 4,
        "description": "A third-party dependency in the registry is assumed to contain malicious code. The simulation "
        "evaluates dependency review, package integrity verification and dependency controls.",
        "business_impact": "Malicious code runs in builds, on developer machines and in production.",
        "asset_categories": "Third-party packages, Build environments, Developer machines, Production services",
        "assumptions": "Builds and developers resolve the latest dependency version. The build publishes artifacts that include the dependency (a cycle back to the registry).",
        "preventive_measures": "Dependency pinning and hash verification, isolated builds, artifact signing.",
        "detective_measures": "Software composition analysis, runtime monitoring, incident response.",
        "rules": [
            ("registry", "ide", 55, "Developers install the dependency locally (reverse path)"),
            ("registry", "cicd", 75, "Builds pull the dependency (reverse path)"),
            ("registry", "production", 70, "Dependency ships inside deployed services"),
            ("cicd", "registry", 60, "Build republishes artifacts containing the dependency (cycle)"),
            ("cicd", "production", 65, "Build deploys artifacts containing the dependency (bypass path)"),
        ],
        "controls": [
            "dependency-pinning",
            "sca",
            "isolated-builds",
            "artifact-signing",
            "runtime-monitoring",
            "incident-response",
        ],
    },
    {
        "slug": "compromised-software-registry",
        "name": "Compromised Software Registry",
        "initial_stage": "registry",
        "likelihood": 45,
        "severity": 5,
        "impact": 5,
        "description": "A registry or publishing credential is assumed to be compromised. The simulation evaluates "
        "unauthorized package publication and inadequate artifact verification.",
        "business_impact": "Tampered packages are distributed under a trusted name to production and to downstream builds.",
        "asset_categories": "Publishing credentials, Packages, Container images, Production services",
        "assumptions": "The attacker can publish new versions. Deployments and some builds consume the latest version.",
        "preventive_measures": "Registry access restrictions, artifact signing and provenance verification, short-lived tokens.",
        "detective_measures": "Publication alerts, software composition analysis, runtime monitoring.",
        "rules": [
            ("registry", "cicd", 50, "Builds consume tampered packages (reverse path)"),
            ("registry", "production", 85, "Deployments pull the tampered artifact"),
            ("cicd", "production", 60, "Build deploys artifacts containing tampered packages (bypass path)"),
        ],
        "controls": [
            "registry-access",
            "artifact-signing",
            "least-privilege",
            "sca",
            "runtime-monitoring",
            "incident-response",
        ],
    },
    {
        "slug": "production-credential-exposure",
        "name": "Production Credential Exposure",
        "initial_stage": "production",
        "likelihood": 65,
        "severity": 5,
        "impact": 5,
        "description": "A production credential is assumed to be exposed, for example in a log file. The simulation "
        "evaluates the immediate impact and possible further consequences through explicit reverse relationships.",
        "business_impact": "Direct access to customer-facing services and data; possible pivot into deployment tooling.",
        "asset_categories": "Production credentials, Runtime services, Customer data",
        "assumptions": "The credential grants operational access. It may also be accepted by the registry or pipeline (lateral reuse).",
        "preventive_measures": "Production secret management with rotation, least privilege, deployment approvals.",
        "detective_measures": "Runtime monitoring, credential-use alerts, incident response and rotation runbooks.",
        "rules": [
            ("production", "cicd", 30, "Credential reused by deployment tooling (reverse path)"),
            ("production", "registry", 35, "Credential can pull/push images (reverse path)"),
        ],
        "controls": ["prod-secrets", "least-privilege", "runtime-monitoring", "deploy-approvals", "incident-response"],
    },
]


# Why each control's effectiveness parameter has the value it has, and what the
# control does not cover. The numbers are illustrative teaching parameters chosen
# for relative plausibility (stronger, harder-to-bypass controls score higher);
# they are not measurements, and no study is claimed as their source.
CONTROL_NOTES = {
    "mfa": (
        "Assumes phishing-resistant or app-based MFA is enforced on every developer and repository account. "
        "Scored high because it removes the most common takeover path (a reused or phished password) on its own.",
        "Does not stop session-token theft, malware on an already signed-in workstation, or MFA-fatigue approval "
        "when push prompts are used. Covers only accounts where it is actually enforced.",
    ),
    "least-privilege": (
        "Assumes access reviews keep each account and token limited to the stages it needs. Scored moderately: "
        "it narrows how far a compromise spreads but does not prevent the first compromise.",
        "Erodes over time without periodic review; break-glass and automation accounts are often exempt; "
        "a compromised administrator is not constrained.",
    ),
    "protected-branches": (
        "Assumes required review by a second person and no direct pushes to the release branch, including for "
        "administrators.",
        "A reviewer can miss obfuscated malicious changes; a compromised reviewer account or an admin bypass "
        "defeats it; it does not protect other branches that feed builds.",
    ),
    "signed-commits": (
        "Assumes commits must be signed with keys bound to verified identities and unsigned commits are rejected. "
        "Scored lower because it proves authorship, not intent.",
        "A stolen signing key, or malicious code committed by the legitimate author, still passes.",
    ),
    "isolated-builds": (
        "Assumes ephemeral, single-use build runners with no state shared between jobs.",
        "Does not protect against a malicious build definition in the repository itself or compromised build "
        "dependencies fetched during the job.",
    ),
    "cicd-secrets": (
        "Assumes short-lived, scoped credentials from a secrets manager, never stored in repository files or "
        "long-lived pipeline variables.",
        "A job that legitimately receives a secret can still leak it while it runs; scope mistakes widen exposure.",
    ),
    "dependency-pinning": (
        "Assumes lockfiles with integrity hashes are enforced in both developer environments and CI, and "
        "updates are reviewed.",
        "Pinning a version that is already malicious preserves the problem; it does not detect a compromised "
        "upstream release that is reviewed and accepted.",
    ),
    "sca": (
        "Detective: assumes software composition analysis runs on every build and findings are triaged. Scored "
        "moderately because it only finds known-bad components.",
        "Cannot detect novel malicious packages or zero-day vulnerabilities; value depends on someone acting on "
        "the findings.",
    ),
    "artifact-signing": (
        "Assumes build artifacts are signed with provenance and that deployment verifies signatures and refuses "
        "unsigned or mismatched artifacts.",
        "A compromised build system can sign malicious output; verification that is optional or warn-only gives "
        "no protection.",
    ),
    "registry-access": (
        "Assumes publishing requires scoped, short-lived tokens tied to the CI identity rather than personal "
        "long-lived tokens.",
        "Does not stop a compromised pipeline that holds the legitimate publishing identity.",
    ),
    "deploy-approvals": (
        "Assumes a human approval gate for production releases with change context shown to the approver.",
        "Approvers rarely inspect artifact contents, so a malicious but well-described release is likely approved; "
        "emergency bypasses weaken it.",
    ),
    "prod-secrets": (
        "Assumes production credentials are short-lived, rotated and issued through a secrets manager with "
        "access logging.",
        "A process that holds a valid credential at runtime can still misuse it; leaked credentials remain "
        "usable until they expire or are revoked.",
    ),
    "runtime-monitoring": (
        "Detective: assumes monitoring of production behaviour with alerts that are investigated. It reduces "
        "impact by shortening dwell time rather than preventing entry.",
        "Depends on detection rules and response capacity; quiet or slow attacks may not trigger alerts.",
    ),
    "incident-response": (
        "Recovery: assumes a rehearsed incident response plan, including credential revocation and artifact "
        "rollback. Scored lowest because it only limits damage after compromise.",
        "Does not reduce the chance of compromise; effectiveness depends on detection happening first.",
    ),
}
