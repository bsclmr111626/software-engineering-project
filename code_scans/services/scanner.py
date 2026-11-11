
import shutil
import stat
import zipfile
import json
import subprocess
import hashlib
import tempfile
from urllib.parse import unquote, urlparse
from pathlib import Path, PurePosixPath

from django.db import transaction
from django.utils import timezone
from django.conf import settings


class ScanArchiveError(Exception):
    """Raised when an uploaded source archive is unsafe or invalid."""


# Directories that are not useful for source analysis and can be very large.
IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".next",
    ".nuxt",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".tox",
    "vendor",
}

SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
}


def _validate_archive_path(name):
    """Validate a ZIP entry path before writing it to disk."""

    if not name or "\x00" in name or "\\" in name:
        raise ScanArchiveError("The archive contains an invalid file path.")

    path = PurePosixPath(name)

    if path.is_absolute():
        raise ScanArchiveError("The archive contains an absolute file path.")

    if any(part in {"", ".", ".."} for part in path.parts):
        raise ScanArchiveError("The archive contains an unsafe file path.")

    # Prevent Windows drive paths and invalid Windows filename characters.
    for part in path.parts:
        if ":" in part or any(char in part for char in '<>:"|?*'):
            raise ScanArchiveError("The archive contains an invalid file name.")

        if part.endswith((" ", ".")):
            raise ScanArchiveError("The archive contains an invalid file name.")

        # Windows reserved device names.
        reserved = {
            "CON", "PRN", "AUX", "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }

        if part.split(".")[0].upper() in reserved:
            raise ScanArchiveError("The archive contains a reserved file name.")

    return path


def _should_ignore(path):
    """Skip dependency, cache and generated directories."""

    return any(
        part.lower() in IGNORED_DIRECTORIES
        for part in path.parts
    )


def extract_source_archive(uploaded_file, destination):
    """
    Safely extract an uploaded ZIP archive into a private directory.

    Returns a set containing the detected CodeQL languages:
    python and/or javascript.
    """

    max_files = settings.CODE_SCAN_MAX_FILES
    max_extracted_size = settings.CODE_SCAN_MAX_EXTRACTED_SIZE
    max_upload_size = settings.CODE_SCAN_MAX_UPLOAD_SIZE

    if uploaded_file.size > max_upload_size:
        raise ScanArchiveError("The uploaded archive exceeds the upload size limit.")

    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=True)

    seen_paths = set()
    extracted_size = 0
    extracted_files = 0
    languages = set()

    try:
        uploaded_file.seek(0)

        with zipfile.ZipFile(uploaded_file, "r") as archive:
            entries = archive.infolist()

            if not entries:
                raise ScanArchiveError("The uploaded ZIP archive is empty.")

            if len(entries) > max_files:
                raise ScanArchiveError("The archive contains too many entries.")

            # Validate all entries before extracting anything.
            for info in entries:
                path = _validate_archive_path(info.filename)

                normalized_name = str(path).casefold()

                if normalized_name in seen_paths:
                    raise ScanArchiveError(
                        "The archive contains duplicate file paths."
                    )

                seen_paths.add(normalized_name)

                if info.flag_bits & 0x1:
                    raise ScanArchiveError(
                        "Password-protected ZIP files are not supported."
                    )

                unix_mode = info.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)

                if file_type == stat.S_IFLNK:
                    raise ScanArchiveError(
                        "Symbolic links are not allowed in uploaded archives."
                    )

                if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ScanArchiveError(
                        "The archive contains an unsupported file type."
                    )

                if info.file_size < 0:
                    raise ScanArchiveError("The archive contains an invalid file.")

                extracted_size += info.file_size

                if extracted_size > max_extracted_size:
                    raise ScanArchiveError(
                        "The extracted archive exceeds the size limit."
                    )

            actual_extracted_size = 0

            # Extract validated files without using ZipFile.extract().
            for info in entries:
                path = _validate_archive_path(info.filename)

                if info.is_dir() or _should_ignore(path):
                    continue

                target = (destination / Path(*path.parts)).resolve()

                if not target.is_relative_to(destination):
                    raise ScanArchiveError(
                        "The archive contains an unsafe file path."
                    )

                target.parent.mkdir(parents=True, exist_ok=True)

                file_size = 0

                with archive.open(info, "r") as source:
                    with target.open("xb") as output:
                        while True:
                            chunk = source.read(1024 * 1024)

                            if not chunk:
                                break

                            file_size += len(chunk)
                            actual_extracted_size += len(chunk)

                            if actual_extracted_size > max_extracted_size:
                                raise ScanArchiveError(
                                    "The extracted archive exceeds the size limit."
                                )

                            if file_size > info.file_size:
                                raise ScanArchiveError(
                                    "The archive contains an invalid file."
                                )

                            output.write(chunk)

                if file_size != info.file_size:
                    raise ScanArchiveError(
                        "The archive contains an incomplete or invalid file."
                    )

                extracted_files += 1

                if target.suffix.lower() == ".py":
                    languages.add("python")

                elif target.suffix.lower() in {
                    ".js", ".jsx", ".ts", ".tsx"
                }:
                    languages.add("javascript")

            if extracted_files == 0:
                raise ScanArchiveError(
                    "The archive contains no extractable files."
                )

            if not languages:
                raise ScanArchiveError(
                    "No supported Python or JavaScript/TypeScript source files "
                    "were found."
                )

            return languages

    except zipfile.BadZipFile as exc:
        raise ScanArchiveError("The uploaded file is not a valid ZIP archive.") from exc

    except (OSError, RuntimeError, EOFError) as exc:
        raise ScanArchiveError(
            "The archive could not be safely extracted."
        ) from exc


class CodeQLExecutionError(Exception):
    """Raised when CodeQL cannot complete a scan."""


CODEQL_SUITES = {
    "python": (
        "codeql/python-queries:"
        "codeql-suites/python-security-extended.qls"
    ),
    "javascript": (
        "codeql/javascript-queries:"
        "codeql-suites/javascript-security-extended.qls"
    ),
}


def _run_command(command, timeout, working_directory):
    """Run CodeQL safely without invoking a shell."""

    try:
        result = subprocess.run(
            command,
            cwd=str(working_directory),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )

    except subprocess.TimeoutExpired as exc:
        raise CodeQLExecutionError(
            "CodeQL exceeded the configured scan time limit."
        ) from exc

    except FileNotFoundError as exc:
        raise CodeQLExecutionError(
            "CodeQL executable was not found. Check CODEQL_EXECUTABLE."
        ) from exc

    if result.returncode != 0:
        # Do not expose potentially sensitive source paths or source contents.
        details = (result.stderr or result.stdout or "").strip()

        raise CodeQLExecutionError(
            "CodeQL failed. "
            + (details[-2000:] if details else "No error details were provided.")
        )

    return result


def run_codeql(source_directory, work_directory, languages):
    """
    Run CodeQL against the supplied source directory.

    Returns a list of dictionaries containing each language and
    its parsed SARIF report.
    """

    executable = Path(settings.CODEQL_EXECUTABLE)

    if not executable.is_file():
        raise CodeQLExecutionError(
            "CodeQL executable was not found. Check CODEQL_EXECUTABLE."
        )

    source_directory = Path(source_directory).resolve()
    work_directory = Path(work_directory).resolve()
    work_directory.mkdir(parents=True, exist_ok=True)

    timeout = settings.CODEQL_TIMEOUT_SECONDS

    reports = []

    # Verify the installed CodeQL CLI.
    version_result = _run_command(
        [str(executable), "version"],
        timeout=30,
        working_directory=work_directory,
    )

    scanner_version = version_result.stdout.strip()[:50]

    for language in sorted(languages):
        if language not in CODEQL_SUITES:
            raise CodeQLExecutionError(
                f"Unsupported CodeQL language: {language}"
            )

        database_directory = work_directory / f"{language}-database"
        sarif_file = work_directory / f"{language}-results.sarif"

        # Create a separate CodeQL database for this language.
        create_command = [
            str(executable),
            "database",
            "create",
            str(database_directory),
            f"--language={language}",
            "--build-mode=none",
            f"--source-root={source_directory}",
        ]

        _run_command(
            create_command,
            timeout=timeout,
            working_directory=work_directory,
        )

        # Run the language-specific security query suite.
        analyze_command = [
            str(executable),
            "database",
            "analyze",
            str(database_directory),
            CODEQL_SUITES[language],
            "--format=sarifv2.1.0",
            f"--output={sarif_file}",
        ]

        _run_command(
            analyze_command,
            timeout=timeout,
            working_directory=work_directory,
        )

        if not sarif_file.is_file():
            raise CodeQLExecutionError(
                f"CodeQL did not produce a SARIF report for {language}."
            )

        try:
            with sarif_file.open("r", encoding="utf-8") as report_file:
                sarif_data = json.load(report_file)

        except (OSError, json.JSONDecodeError) as exc:
            raise CodeQLExecutionError(
                f"CodeQL produced an invalid SARIF report for {language}."
            ) from exc

        if not isinstance(sarif_data, dict):
            raise CodeQLExecutionError(
                f"The SARIF report for {language} has an invalid structure."
            )

        reports.append({
            "language": language,
            "scanner_version": scanner_version,
            "sarif": sarif_data,
        })

    return reports


def _map_severity(result, rule):
    """Convert SARIF severity information into CodeGuard severity levels."""

    result_properties = result.get("properties") or {}
    rule_properties = rule.get("properties") or {}

    # CodeQL commonly provides security-severity as a numeric string.
    raw_security_severity = (
        result_properties.get("security-severity")
        or rule_properties.get("security-severity")
    )

    if raw_security_severity is not None:
        try:
            score = float(raw_security_severity)

            if score >= 9.0:
                return "critical"
            if score >= 7.0:
                return "high"
            if score >= 4.0:
                return "medium"
            if score > 0:
                return "low"

        except (TypeError, ValueError):
            pass

    # Fall back to the SARIF result level.
    level = (result.get("level") or "").lower()

    return {
        "error": "high",
        "warning": "medium",
        "note": "low",
        "none": "note",
    }.get(level, "warning")


def _get_finding_file_path(uri, source_directory):
    """Return a safe path relative to the extracted source directory."""

    if not uri:
        return ""

    parsed = urlparse(uri)

    if parsed.scheme and parsed.scheme != "file":
        return ""

    raw_path = unquote(parsed.path if parsed.scheme == "file" else uri)

    # Handle Windows file URIs such as file:///C:/project/file.py.
    if len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == ":":
        raw_path = raw_path[1:]

    try:
        candidate = Path(raw_path)

        if candidate.is_absolute():
            candidate = candidate.resolve()
            relative = candidate.relative_to(source_directory.resolve())
        else:
            normalized = raw_path.replace("\\", "/")
            relative_path = PurePosixPath(normalized)

            if relative_path.is_absolute():
                return ""

            if any(part in {"", ".", ".."} for part in relative_path.parts):
                return ""

            relative = Path(*relative_path.parts)

        return relative.as_posix()[:1000]

    except (ValueError, OSError):
        return ""


def _get_fingerprint(result, rule_id, file_path, start_line, message):
    """Build a stable fingerprint for identifying a finding."""

    partial_fingerprints = result.get("partialFingerprints") or {}
    fingerprints = result.get("fingerprints") or {}

    for collection in (partial_fingerprints, fingerprints):
        if isinstance(collection, dict):
            for value in collection.values():
                if isinstance(value, str) and value:
                    return value[:255]

    # Fallback when CodeQL does not supply a fingerprint.
    raw = "|".join([
        rule_id,
        file_path,
        str(start_line or ""),
        message,
    ])

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_sarif(sarif_data, source_directory):
    """
    Convert SARIF results into dictionaries suitable for CodeFinding creation.

    One dictionary is returned for each finding.
    """

    if not isinstance(sarif_data, dict):
        raise CodeQLExecutionError("The SARIF report has an invalid structure.")

    runs = sarif_data.get("runs", [])

    if not isinstance(runs, list):
        raise CodeQLExecutionError("The SARIF report contains invalid runs.")

    findings = []

    for run in runs:
        if not isinstance(run, dict):
            continue

        driver = run.get("tool", {}).get("driver", {})
        rules = driver.get("rules", [])

        if not isinstance(rules, list):
            rules = []

        rules_by_id = {}

        for rule in rules:
            if isinstance(rule, dict) and rule.get("id"):
                rules_by_id[rule["id"]] = rule

        results = run.get("results", [])

        if not isinstance(results, list):
            continue

        for result in results:
            if not isinstance(result, dict):
                continue

            rule_id = str(result.get("ruleId") or "unknown")[:255]

            rule = rules_by_id.get(rule_id, {})

            rule_name = (
                rule.get("name")
                or rule.get("shortDescription", {}).get("text")
                or rule_id
            )

            message_data = result.get("message") or {}

            message = (
                message_data.get("text")
                or message_data.get("markdown")
                or rule_name
            )

            message = str(message)

            severity = _map_severity(result, rule)

            locations = result.get("locations") or []
            physical_location = {}

            if locations:
                physical_location = (
                    locations[0]
                    .get("physicalLocation", {})
                )

            artifact_location = (
                physical_location.get("artifactLocation", {})
            )

            file_path = _get_finding_file_path(
                artifact_location.get("uri", ""),
                Path(source_directory).resolve(),
            )

            region = physical_location.get("region") or {}

            def positive_integer(value):
                try:
                    number = int(value)
                    return number if number > 0 else None
                except (TypeError, ValueError):
                    return None

            start_line = positive_integer(region.get("startLine"))
            end_line = positive_integer(region.get("endLine"))
            start_column = positive_integer(region.get("startColumn"))
            end_column = positive_integer(region.get("endColumn"))

            rule_properties = rule.get("properties") or {}

            tags = rule_properties.get("tags") or []

            if not isinstance(tags, list):
                tags = []

            tags = [
                str(tag)[:100]
                for tag in tags
                if isinstance(tag, (str, int, float))
            ][:30]

            help_uri = (
                rule.get("helpUri")
                or rule.get("help", {}).get("text", "")
            )

            # Only retain selected metadata, not the entire SARIF result.
            properties = {}

            for key in (
                "security-severity",
                "precision",
                "kind",
                "problem.severity",
            ):
                value = (
                    result.get("properties", {}).get(key)
                    or rule_properties.get(key)
                )

                if value is not None:
                    properties[key] = value

            fingerprint = _get_fingerprint(
                result,
                rule_id,
                file_path,
                start_line,
                message,
            )

            findings.append({
                "rule_id": rule_id,
                "rule_name": str(rule_name)[:255],
                "message": message,
                "severity": severity,
                "file_path": file_path,
                "start_line": start_line,
                "end_line": end_line,
                "start_column": start_column,
                "end_column": end_column,
                "help_uri": (
                    str(help_uri)[:1000]
                    if isinstance(help_uri, str)
                    and help_uri.startswith(("http://", "https://"))
                    else ""
                ),
                "fingerprint": fingerprint,
                "tags": tags,
                "properties": properties,
            })

    return findings


def save_scan_results(scan, reports, source_directory):
    """
    Parse SARIF reports and save all findings for a completed scan.

    Findings and scan totals are committed together so the database
    does not contain partially imported results.
    """

    from code_scans.models import CodeFinding, CodeScan

    if not reports:
        raise CodeQLExecutionError(
            "CodeQL did not produce any language reports."
        )

    all_findings = []
    scanner_versions = set()
    detected_languages = set()

    for report in reports:
        language = report["language"]
        sarif_data = report["sarif"]

        detected_languages.add(language)

        version = report.get("scanner_version", "")
        if version:
            scanner_versions.add(version)

        parsed_findings = parse_sarif(
            sarif_data,
            source_directory,
        )

        all_findings.extend(parsed_findings)

    # Prevent an unexpectedly large report from exhausting memory or
    # creating an excessive number of database records.
    if len(all_findings) > 20000:
        raise CodeQLExecutionError(
            "The scan produced too many findings to import safely."
        )

    severity_counts = {
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0,
    }

    finding_objects = []

    for finding in all_findings:
        severity = finding["severity"]

        if severity in severity_counts:
            severity_counts[severity] += 1

        finding_objects.append(
            CodeFinding(
                scan=scan,
                **finding,
            )
        )

    with transaction.atomic():
        # Remove any previous results if this scan is being reprocessed.
        CodeFinding.objects.filter(scan=scan).delete()

        CodeFinding.objects.bulk_create(
            finding_objects,
            batch_size=500,
        )

        scan.total_findings = len(finding_objects)
        scan.critical_findings = severity_counts["critical"]
        scan.high_findings = severity_counts["high"]
        scan.medium_findings = severity_counts["medium"]
        scan.low_findings = severity_counts["low"]

        scan.languages = sorted(detected_languages)

        scan.scanner_version = ", ".join(
            sorted(scanner_versions)
        )[:50]

        scan.status = CodeScan.Status.COMPLETED
        scan.completed_at = timezone.now()
        scan.error_message = ""

        scan.save(update_fields=[
            "total_findings",
            "critical_findings",
            "high_findings",
            "medium_findings",
            "low_findings",
            "languages",
            "scanner_version",
            "status",
            "completed_at",
            "error_message",
        ])

    return scan


def mark_scan_failed(scan, error):
    """Mark a scan as failed and remove any incomplete findings."""

    from code_scans.models import CodeFinding, CodeScan

    with transaction.atomic():
        CodeFinding.objects.filter(scan=scan).delete()

        scan.status = CodeScan.Status.FAILED
        scan.completed_at = timezone.now()

        # Store a limited error message, not source code or temporary paths.
        scan.error_message = str(error)[:2000]

        scan.total_findings = 0
        scan.critical_findings = 0
        scan.high_findings = 0
        scan.medium_findings = 0
        scan.low_findings = 0

        scan.save(update_fields=[
            "status",
            "completed_at",
            "error_message",
            "total_findings",
            "critical_findings",
            "high_findings",
            "medium_findings",
            "low_findings",
        ])

    return scan


def process_code_scan(scan, uploaded_file):
    """
    Execute the complete source-code scanning workflow.

    The uploaded archive and CodeQL databases are kept in a temporary
    directory and deleted when the function finishes.
    """

    from code_scans.models import CodeScan

    scan.status = CodeScan.Status.RUNNING
    scan.started_at = timezone.now()
    scan.completed_at = None
    scan.error_message = ""

    scan.save(update_fields=[
        "status",
        "started_at",
        "completed_at",
        "error_message",
    ])

    try:
        with tempfile.TemporaryDirectory(
            prefix="codeguard_scan_",
            ignore_cleanup_errors=True,
        ) as temporary_directory:

            temporary_root = Path(temporary_directory)

            source_directory = temporary_root / "source"
            work_directory = temporary_root / "codeql"

            source_directory.mkdir()
            work_directory.mkdir()

            # Validate and safely extract the uploaded archive.
            languages = extract_source_archive(
                uploaded_file,
                source_directory,
            )

            scan.languages = sorted(languages)
            scan.save(update_fields=["languages"])

            # Execute CodeQL for the detected languages.
            reports = run_codeql(
                source_directory,
                work_directory,
                languages,
            )

            # Import all SARIF findings into the database.
            save_scan_results(
                scan,
                reports,
                source_directory,
            )

        # TemporaryDirectory automatically removes the extracted source,
        # CodeQL databases and SARIF reports here.

        return scan

    except Exception as exc:
        mark_scan_failed(scan, exc)
        raise



