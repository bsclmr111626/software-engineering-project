# Diagram: data flow

Where data comes from, where it is stored and what reads it. Rectangles are code, cylinders are
tables (or JSON columns), parallelograms are outputs.

```mermaid
flowchart LR
    seed["seed_codeguard<br/>threats/seed_data.py"] --> stages[("threats_supplychainstage")]
    seed --> controls[("threats_securitycontrol<br/>+ _stages")]
    seed --> scen[("threats_threatscenario<br/>threats_propagationrule<br/>threats_scenariocontrol")]
    form["Scenario form + rule formset<br/>threats/forms.py"] -->|save_scenario| scen

    cfg["SimulationForm<br/>simulation/forms.py"] --> svc["run_simulation<br/>simulation/services.py"]
    stages --> build["build_input"]
    scen --> build
    controls --> build
    svc --> build --> inp["SimulationInput (frozen dataclasses)"]
    inp --> engine["engine.simulate"] --> res["SimulationResult"]
    inp --> recs["recommend / control_contributions"]
    res --> recs
    controls -->|catalog| recs

    svc --> run[("simulation_simulationrun<br/>input_snapshot JSON, result JSON,<br/>headline scores")]
    res --> stage_rows[("simulation_simulationstageresult")]
    res --> events[("simulation_propagationevent")]
    recs --> run

    run --> detail[/"Result pages, report document"/]
    stage_rows --> detail
    events --> detail
    run --> png[/"Matplotlib PNG charts"/]
    stage_rows --> png
    events --> png
    run --> csv[/"CSV exports"/]
    stage_rows --> dash[/"Overview, supply-chain map, risk analysis"/]
    run --> dash

    run -->|recommendation chosen| rem[("remediation_remediationitem")]
    rem --> plan[/"Remediation plan + verification"/]
    run --> plan

    svc --> audit[("audit_auditevent")]
    audit --> log[/"Audit log, security page,<br/>notifications, sign-in throttling"/]
```

Key property: report pages read only stored rows and JSON (`SimulationRun.input_snapshot`,
`result`, stage results, events). Editing or deleting the scenario later does not change them;
`simulation.services.input_from_snapshot` can rebuild the exact engine input.
