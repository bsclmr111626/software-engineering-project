# Reference: migrations

15 CodeGuard migration files across 5 apps (the `core` app has no models and no migrations).
Verified on 2026-11-10: `manage.py makemigrations --check --dry-run` → "No changes detected";
`manage.py migrate` on an empty scratch database applied every migration without error, and
`showmigrations` marked all of them `[X]`.

| App | Migration | Generated | Depends on | Operations | Kind |
|---|---|---|---|---|---|
| accounts | `0001_initial` | 2026-10-26 | `AUTH_USER_MODEL` | `CreateModel Profile` with `profile_role_valid` CHECK | schema |
| accounts | `0002_preferences` | 2026-10-28 | `accounts.0001`, `AUTH_USER_MODEL` | `AddField profile.job_title`, `AddField profile.team`, `CreateModel UserPreference` with `preference_page_size_valid` | schema |
| accounts | `0003_surface_preference` | 2026-10-28 | `accounts.0002` | `AddField userpreference.surface` (choices paper, neutral) | schema |
| accounts | `0004_pearl_surface` | 2026-10-28 | `accounts.0003` | `AlterField surface` (adds `pearl`) | choices only (no SQL on SQLite) |
| accounts | `0005_sage_surface` | 2026-10-28 | `accounts.0004` | `AlterField surface` (adds `sage`) | choices only |
| accounts | `0006_retire_neutral_surface` | 2026-10-28 | `accounts.0005` | `RunPython move_neutral_to_paper` (reverse: `noop`), then `AlterField surface` (paper, pearl, sage) | **data** + choices |
| audit | `0001_initial` | 2026-10-26 | `AUTH_USER_MODEL` | `CreateModel AuditEvent` (16 actions) with index `audit_audit_actor_i_fb4253_idx` | schema |
| audit | `0002_new_security_actions` | 2026-10-26 | `audit.0001` | `AlterField action` (+ `login_throttled`, `audit_purge`) | choices only |
| audit | `0003_remediation_actions` | 2026-10-26 | `audit.0002` | `AlterField action` (+ `remediation_create`, `remediation_update`) | choices only |
| audit | `0004_account_actions` | 2026-10-28 | `audit.0003` | `AlterField action` (+ `profile_update`, `email_change`, `preferences_update`, `sessions_revoked`, `data_export`; 25 total) | choices only |
| threats | `0001_initial` | 2026-10-26 | `AUTH_USER_MODEL` | `CreateModel` for `SecurityControl`, `ScenarioControl`, `SupplyChainStage`, `ThreatScenario`, `PropagationRule`, plus their constraints and indexes | schema |
| threats | `0002_friendly_rule_constraint_messages` | 2026-10-26 | `threats.0001` | `AlterConstraint` × 2 (adds `violation_error_message` to `unique_rule_per_edge`, `rule_not_self_loop`) | Python-side message only |
| threats | `0003_control_assumptions` | 2026-10-26 | `threats.0002` | `AddField securitycontrol.effectiveness_basis`, `AddField securitycontrol.limitations` | schema (table rebuild on SQLite) |
| simulation | `0001_initial` | 2026-10-26 | `threats.0001`, `AUTH_USER_MODEL` | `CreateModel` for `SimulationRun`, `SimulationStageResult`, `PropagationEvent`, constraints and indexes | schema |
| remediation | `0001_initial` | not stated in file header | `simulation.0001`, `threats.0003`, `AUTH_USER_MODEL` | `CreateModel RemediationItem`, partial unique constraint, check constraint, index | schema |

Notes:

- The `AuditAction` enum in `audit/models.py` has 25 members and `audit.0004` lists the same 25
  choices, which is why `makemigrations --check` finds nothing to do. Choices are part of a
  field's definition, so every new audit action needs a new `AlterField` migration even though
  no SQL changes (that is what `audit.0002`–`0004` are).
- Mixed quoting styles (`'…'` in files kept as generated, `"…"` in files reformatted by hand)
  are cosmetic. Ruff excludes `*/migrations/*` (`pyproject.toml`).
- `remediation.0001` depends on `threats.0003` because `RemediationItem.control` points at
  `SecurityControl` in its post-`0003` shape.
