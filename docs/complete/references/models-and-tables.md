# Reference: models and database tables

Source of truth: the `models.py` file of each app. Table names were listed from a database built
from scratch with `manage.py migrate` on 2026-11-10 (23 tables, below). Django names a table
`<app_label>_<lowercase model name>`.

## CodeGuard tables (12 models, 13 tables)

| Table | Model (file) | Purpose | Key fields and relations | Constraints and indexes |
|---|---|---|---|---|
| `accounts_profile` | `Profile` (`accounts/models.py`) | The user's CodeGuard role plus optional profile details | `user` one-to-one → `auth_user` (CASCADE); `role` (`admin`/`analyst`/`viewer`, default `viewer`); `job_title`, `team` | `profile_role_valid` CHECK (role in the three values) |
| `accounts_userpreference` | `UserPreference` (`accounts/models.py`) | Interface, notification and session preferences | `user` one-to-one → `auth_user` (CASCADE); `color_mode`, `accent`, `surface`, `text_size`, `heading_font`, `density`, `timestamp_style`, `page_size`, `start_page`; three accessibility booleans; three `notify_*` booleans; `notifications_seen_at`; `share_reports_by_default`; `session_epoch` | `preference_page_size_valid` CHECK (10, 25, 50) |
| `audit_auditevent` | `AuditEvent` (`audit/models.py`) | Append-only audit trail | `actor` FK → `auth_user` (SET_NULL, nullable); `actor_username`; `action` (25 choices, indexed); `object_type`, `object_id`, `object_repr`; `metadata` JSON; `ip_address`; `created_at` (indexed) | Index (`actor`, `-created_at`). Append-only enforced in Python (`save`, `delete`, `AppendOnlyQuerySet`), not in SQL |
| `threats_supplychainstage` | `SupplyChainStage` (`threats/models.py`) | The five ordered stages | `key` (unique slug), `name`, `position` (unique), `description`, `assets`, `icon`, `weight` (1–5) | `stage_weight_range` CHECK |
| `threats_securitycontrol` | `SecurityControl` (`threats/models.py`) | Control catalogue | `slug` (unique), `name`, `description`, `category` (preventive/detective/recovery), `effectiveness` (0–100), `effort`, `priority`, `addresses`, `effectiveness_basis`, `limitations` | `control_effectiveness_range` CHECK (≤ 100; ≥ 0 comes from the unsigned column) |
| `threats_securitycontrol_stages` | auto M2M table for `SecurityControl.stages` | Which stages a control protects | `securitycontrol_id`, `supplychainstage_id` | Unique pair (Django default) |
| `threats_threatscenario` | `ThreatScenario` (`threats/models.py`) | A hypothetical attack used as simulation input | `slug` (unique), `name`, `description`, `initial_stage` FK → stage (PROTECT); `likelihood`, `severity`, `impact`, `propagation_threshold`; narrative text fields; `owner` FK → `auth_user` (CASCADE, nullable); `visibility` (shared/private); `status` (active/archived); `is_system`; `version`; `controls` M2M through `ScenarioControl` | CHECKs: `scenario_likelihood_range`, `scenario_severity_range`, `scenario_impact_range`, `scenario_threshold_range`, `private_scenario_has_owner`. Index (`status`, `visibility`) |
| `threats_propagationrule` | `PropagationRule` (`threats/models.py`) | A directed edge of one scenario's graph | `scenario` FK (CASCADE); `source`, `target` FK → stage (PROTECT); `probability` (0–100); `rationale` | `unique_rule_per_edge` UNIQUE (scenario, source, target); `rule_not_self_loop` CHECK; `rule_probability_range` CHECK |
| `threats_scenariocontrol` | `ScenarioControl` (`threats/models.py`) | Marks a control as relevant to a scenario | `scenario` FK (CASCADE); `control` FK (PROTECT); `note` | `unique_scenario_control` UNIQUE |
| `simulation_simulationrun` | `SimulationRun` (`simulation/models.py`) | One execution of the engine | `id` UUID primary key; `user` FK (CASCADE); `scenario` FK (SET_NULL, nullable); denormalised `scenario_name`, `scenario_slug`, `scenario_version`, `entry_stage_name`; `status` (pending/completed/failed); `error_message`; `is_shared`; inputs `likelihood`, `severity`, `impact`, `threshold`, `enabled_controls` (JSON list); outputs `inherent_risk`, `residual_risk`, `classification`, `compromised_count`, `blocked_count`; `input_snapshot` JSON; `result` JSON; `created_at`, `completed_at` | `run_residual_risk_range` CHECK (NULL or 0–100). Indexes (`user`, `-created_at`), (`is_shared`, `status`); `status` and `created_at` indexed |
| `simulation_simulationstageresult` | `SimulationStageResult` (`simulation/models.py`) | Per-stage outcome of a run | `run` FK (CASCADE); `stage_key`, `stage_name`, `position`, `state`, `inherent_state`, likelihoods, coverages, risks, `classification`, `explanation` | `unique_stage_per_run` UNIQUE (run, stage_key); index (`stage_key`, `state`) |
| `simulation_propagationevent` | `PropagationEvent` (`simulation/models.py`) | One evaluated edge in a run | `run` FK (CASCADE); `order`; source/target key and name; `kind`; `base_probability`, `control_coverage`, `effective_probability`, `threshold`; `outcome`; `target_already_compromised`; `transmitted_likelihood`; `controls_applied` JSON; `explanation` (≤ 300 chars) | `unique_event_order_per_run` UNIQUE (run, order) |
| `remediation_remediationitem` | `RemediationItem` (`remediation/models.py`) | A recommended control an analyst committed to act on | `owner` FK (CASCADE); `control` FK (PROTECT); `scenario` FK (SET_NULL); `scenario_slug`, `scenario_name`; `source_run` FK (SET_NULL); `baseline_risk`, `expected_reduction`; `status` (open/in_progress/done/risk_accepted); `note`, `due_date`, `closed_at` | Partial UNIQUE `one_active_item_per_control_and_scenario` (owner, scenario_slug, control) WHERE status in (open, in_progress); `remediation_reduction_non_negative` CHECK; index (`owner`, `status`) |

There is one more table than models because `SecurityControl.stages` creates an implicit join
table.

## Django framework tables (10)

`auth_user`, `auth_group`, `auth_group_permissions`, `auth_permission`, `auth_user_groups`,
`auth_user_user_permissions`, `django_admin_log`, `django_content_type`, `django_migrations`,
`django_session`. CodeGuard uses the built-in `auth.User`: there is no custom user model. Roles
are not Django groups or permissions; they live in `accounts_profile.role`. The `auth_group*` and
`auth_*permissions` tables exist only because `django.contrib.auth` and the admin install them.

13 CodeGuard tables plus 10 framework tables give the 23 names in the fresh database:

```
accounts_profile              django_admin_log                   simulation_simulationstageresult
accounts_userpreference       django_content_type                threats_propagationrule
audit_auditevent              django_migrations                  threats_scenariocontrol
auth_group                    django_session                     threats_securitycontrol
auth_group_permissions        remediation_remediationitem        threats_securitycontrol_stages
auth_permission               simulation_propagationevent        threats_supplychainstage
auth_user                     simulation_simulationrun           threats_threatscenario
auth_user_groups
auth_user_user_permissions
```

## Delete behaviour (on_delete) at a glance

| Deleting… | Effect |
|---|---|
| a user | Their profile, preferences, private scenarios, runs (and the runs' stage results and events) and remediation items are deleted (CASCADE). Their audit events stay; `actor` becomes NULL and `actor_username` keeps the name. |
| a scenario | Its rules and scenario-control links are deleted. Runs and remediation items keep their denormalised name and slug; their `scenario` link becomes NULL. System scenarios cannot be deleted through the app (`threats.services.can_delete`) or the admin (`ThreatScenarioAdmin.has_delete_permission`). |
| a stage | Refused while any scenario or rule uses it (PROTECT). |
| a control | Refused while a scenario link or remediation item uses it (PROTECT). |
| a run | Its stage results and events are deleted; remediation items keep their data and `source_run` becomes NULL. The app has no "delete run" view. |
