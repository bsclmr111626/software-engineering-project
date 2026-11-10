# Diagram: entity-relationship model

Only CodeGuard tables and `auth_user` are shown. Field lists are abbreviated to keys and the
fields that matter for relationships and rules; the full list is in
`references/models-and-tables.md`.

```mermaid
erDiagram
    auth_user ||--|| accounts_profile : "has role"
    auth_user ||--o| accounts_userpreference : "has preferences"
    auth_user ||--o{ threats_threatscenario : "owns (private)"
    auth_user ||--o{ simulation_simulationrun : "runs"
    auth_user ||--o{ remediation_remediationitem : "owns"
    auth_user |o--o{ audit_auditevent : "actor (SET_NULL)"

    threats_supplychainstage ||--o{ threats_threatscenario : "initial_stage (PROTECT)"
    threats_supplychainstage ||--o{ threats_propagationrule : "source (PROTECT)"
    threats_supplychainstage ||--o{ threats_propagationrule : "target (PROTECT)"
    threats_securitycontrol }o--o{ threats_supplychainstage : "protects (M2M _stages)"
    threats_threatscenario ||--o{ threats_propagationrule : "rules (CASCADE)"
    threats_threatscenario ||--o{ threats_scenariocontrol : "relevant controls"
    threats_securitycontrol ||--o{ threats_scenariocontrol : "PROTECT"

    threats_threatscenario |o--o{ simulation_simulationrun : "scenario (SET_NULL)"
    simulation_simulationrun ||--o{ simulation_simulationstageresult : "stage_results (CASCADE)"
    simulation_simulationrun ||--o{ simulation_propagationevent : "events (CASCADE)"

    threats_securitycontrol ||--o{ remediation_remediationitem : "control (PROTECT)"
    threats_threatscenario |o--o{ remediation_remediationitem : "scenario (SET_NULL)"
    simulation_simulationrun |o--o{ remediation_remediationitem : "source_run (SET_NULL)"

    accounts_profile {
        bigint id PK
        int user_id FK "unique"
        varchar role "admin|analyst|viewer"
    }
    accounts_userpreference {
        bigint id PK
        int user_id FK "unique"
        int session_epoch
        int page_size "10|25|50"
    }
    audit_auditevent {
        bigint id PK
        int actor_id FK "nullable"
        varchar actor_username
        varchar action "25 choices"
        json metadata
        inet ip_address
        datetime created_at
    }
    threats_supplychainstage {
        bigint id PK
        slug key UK
        smallint position UK
        smallint weight "1-5"
    }
    threats_securitycontrol {
        bigint id PK
        slug slug UK
        varchar category "preventive|detective|recovery"
        smallint effectiveness "0-100"
    }
    threats_threatscenario {
        bigint id PK
        slug slug UK
        bigint initial_stage_id FK
        int owner_id FK "nullable"
        varchar visibility "shared|private"
        varchar status "active|archived"
        bool is_system
        int version
    }
    threats_propagationrule {
        bigint id PK
        bigint scenario_id FK
        bigint source_id FK
        bigint target_id FK
        smallint probability "0-100"
    }
    threats_scenariocontrol {
        bigint id PK
        bigint scenario_id FK
        bigint control_id FK
    }
    simulation_simulationrun {
        uuid id PK
        int user_id FK
        bigint scenario_id FK "nullable"
        varchar scenario_slug
        varchar status "pending|completed|failed"
        bool is_shared
        json input_snapshot
        json result
        float residual_risk "NULL or 0-100"
    }
    simulation_simulationstageresult {
        bigint id PK
        uuid run_id FK
        slug stage_key "unique per run"
        varchar state
        float residual_risk
    }
    simulation_propagationevent {
        bigint id PK
        uuid run_id FK
        smallint order "unique per run"
        varchar outcome
        float effective_probability
    }
    remediation_remediationitem {
        bigint id PK
        int owner_id FK
        bigint control_id FK
        bigint scenario_id FK "nullable"
        uuid source_run_id FK "nullable"
        varchar status "open|in_progress|done|risk_accepted"
        float expected_reduction ">= 0"
    }
```

Stage results and events store stage **keys and names as text**, not foreign keys to
`threats_supplychainstage`. That is deliberate: a historical report must survive later changes
to the stage catalogue.
