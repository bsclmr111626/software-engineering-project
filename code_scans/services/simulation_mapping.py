"""Map CodeQL findings to relevant application threat scenarios."""

# Exact CodeQL rule IDs take precedence over CWE-based fallback mappings.
RULE_SCENARIO_MAP = {
    # Command injection
    "py/command-line-injection": "application-command-injection",
    "js/command-line-injection": "application-command-injection",
    # SQL injection
    "js/sql-injection": "application-sql-injection",
    # Path traversal / path injection
    "js/path-injection": "application-path-traversal",
}

# CWE identifiers extracted from CodeQL SARIF tags.
CWE_SCENARIO_MAP = {
    # Command injection
    "cwe-078": "application-command-injection",
    "cwe-088": "application-command-injection",
    # SQL injection
    "cwe-089": "application-sql-injection",
    "cwe-090": "application-sql-injection",
    "cwe-943": "application-sql-injection",
    # Path traversal
    "cwe-022": "application-path-traversal",
    "cwe-023": "application-path-traversal",
    "cwe-036": "application-path-traversal",
    "cwe-073": "application-path-traversal",
    "cwe-099": "application-path-traversal",
}


def scenario_slug_for_finding(finding):
    """
    Return the suggested threat scenario slug for a CodeQL finding.

    A finding indicates a potential weakness, not confirmed exploitation.
    Return None when there is no sufficiently specific mapping.
    """
    rule_id = (finding.rule_id or "").strip().lower()

    # Prefer exact rule mappings.
    scenario_slug = RULE_SCENARIO_MAP.get(rule_id)
    if scenario_slug:
        return scenario_slug

    # Fall back to recognized CWE identifiers in SARIF tags.
    tags = finding.tags or []

    for tag in tags:
        normalized_tag = str(tag).strip().lower()

        if normalized_tag.startswith("external/cwe/"):
            cwe_id = normalized_tag.rsplit("/", 1)[-1]
        else:
            cwe_id = normalized_tag

        scenario_slug = CWE_SCENARIO_MAP.get(cwe_id)
        if scenario_slug:
            return scenario_slug

    return None
