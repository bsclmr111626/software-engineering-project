# Diagram: propagation algorithm

## Activity view of `simulation.propagation.traverse`

```mermaid
flowchart TD
    start(["traverse(stages, edges, entry, entry_likelihood,<br/>coverage, controls_by_stage, threshold)"])
    start --> sort["Group edges by source;<br/>sort each group by target position"]
    sort --> init["compromised = {entry}; queue = [entry]"]
    init --> more{"queue empty?"}
    more -- no --> pop["source = queue.popleft()"]
    pop --> each["for each outgoing edge"]
    each --> eff["effective = p × (1 − preventive coverage of target / 100)"]
    eff --> t1{"effective ≥ threshold?<br/>(rounded to 6 dp)"}
    t1 -- yes --> prop["outcome = propagated"]
    t1 -- no --> t2{"p ≥ threshold?"}
    t2 -- yes --> blk["outcome = blocked_by_controls"]
    t2 -- no --> below["outcome = below_threshold"]
    prop --> newq{"target already compromised?"}
    newq -- no --> add["add target; enqueue it"]
    newq -- yes --> rec
    add --> rec["append EdgeEvaluation (order n)"]
    blk --> rec
    below --> rec
    rec --> each
    each -- "no more edges" --> more
    more -- yes --> lik["_path_likelihoods: max-product path<br/>over propagated edges (Dijkstra variant)"]
    lik --> tx["transmitted = likelihood(source) × effective / 100<br/>for every evaluation"]
    tx --> states["State per stage: entry, compromised,<br/>blocked (any blocked incoming edge),<br/>exposed (other incoming edges), unaffected"]
    states --> fail["Non-compromised stages: likelihood =<br/>max transmitted over incoming attempts"]
    fail --> done(["TraversalResult(states, likelihoods, evaluations)"])
```

## The seeded "Compromised Developer Account" graph

Edge labels are the scenario's propagation probabilities (`threats/seed_data.py`). Edge kinds come
from `edge_kind`: next position = forward, later position = bypass, earlier = reverse.

```mermaid
flowchart LR
    ide["IDE / Developer Environment<br/>pos 1, weight 1 — ENTRY"]
    vcs["Version Control<br/>pos 2, weight 2"]
    cicd["CI/CD Pipeline<br/>pos 3, weight 2"]
    reg["Software Registry<br/>pos 4, weight 2"]
    prod["Production<br/>pos 5, weight 3"]
    ide -->|"85% forward"| vcs
    ide -->|"40% bypass"| cicd
    vcs -->|"80% forward"| cicd
    cicd -->|"70% forward"| reg
    reg -->|"65% forward"| prod
```

With no controls and threshold 50 %, every edge except `ide → cicd` (40 % < 50 %) propagates and
all five stages are compromised. The worked example in `SIMULATION_AND_RISK_METHODOLOGY.md` adds
MFA, protected branches and SCA, which block `ide → vcs` and leave only the entry stage
compromised.
