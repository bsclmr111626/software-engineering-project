"""Deterministic graph traversal that decides how far a compromise spreads.

Algorithm (breadth-first from the entry stage):

1. The entry stage is compromised by assumption.
2. Every outgoing edge of a compromised stage is evaluated exactly once:
       effective probability = edge probability x (1 - preventive coverage of target / 100)
3. The edge propagates when effective probability >= threshold.
   Otherwise it is "blocked by controls" (it would have propagated without
   them) or "below threshold" (it would not have propagated anyway).
4. Newly compromised stages are queued; already-compromised stages are never
   re-queued, so cycles terminate.
5. Stage likelihoods follow the most likely successful path
   (max over paths of the product of effective probabilities).
"""

import heapq
from collections import defaultdict, deque
from dataclasses import dataclass, field

from .risk import meets_threshold

STATE_ENTRY = "entry"
STATE_COMPROMISED = "compromised"
STATE_BLOCKED = "blocked"
STATE_EXPOSED = "exposed"
STATE_UNAFFECTED = "unaffected"

COMPROMISED_STATES = (STATE_ENTRY, STATE_COMPROMISED)

OUTCOME_PROPAGATED = "propagated"
OUTCOME_BLOCKED = "blocked_by_controls"
OUTCOME_BELOW_THRESHOLD = "below_threshold"

KIND_FORWARD = "forward"
KIND_BYPASS = "bypass"
KIND_REVERSE = "reverse"


def edge_kind(source_position, target_position):
    """Classify an edge by the stage positions it connects."""
    if target_position == source_position + 1:
        return KIND_FORWARD
    if target_position > source_position:
        return KIND_BYPASS
    return KIND_REVERSE


@dataclass
class EdgeEvaluation:
    order: int
    source: str
    target: str
    kind: str
    base_probability: float
    target_coverage: float
    effective_probability: float
    threshold: float
    outcome: str
    target_already_compromised: bool
    controls: tuple = ()
    transmitted_likelihood: float = 0.0


@dataclass
class TraversalResult:
    states: dict
    likelihoods: dict
    evaluations: list = field(default_factory=list)


def traverse(stages, edges, entry, entry_likelihood, coverage, controls_by_stage, threshold):
    """Run the propagation traversal.

    stages            -- dict of stage key -> Stage
    edges             -- iterable of Edge
    entry             -- key of the entry stage
    entry_likelihood  -- likelihood (0-100) that the entry stage is compromised
    coverage          -- dict of stage key -> preventive coverage percentage
    controls_by_stage -- dict of stage key -> tuple of preventive control keys
    threshold         -- propagation threshold percentage
    """
    outgoing = defaultdict(list)
    for edge in edges:
        outgoing[edge.source].append(edge)
    for edge_list in outgoing.values():
        edge_list.sort(key=lambda e: stages[e.target].position)

    compromised = {entry}
    queue = deque([entry])
    evaluations = []

    while queue:
        source = queue.popleft()
        for edge in outgoing.get(source, ()):
            target_coverage = coverage.get(edge.target, 0.0)
            effective = edge.probability * (1 - target_coverage / 100)
            if meets_threshold(effective, threshold):
                outcome = OUTCOME_PROPAGATED
            elif meets_threshold(edge.probability, threshold):
                outcome = OUTCOME_BLOCKED
            else:
                outcome = OUTCOME_BELOW_THRESHOLD

            already = edge.target in compromised
            if outcome == OUTCOME_PROPAGATED and not already:
                compromised.add(edge.target)
                queue.append(edge.target)

            evaluations.append(
                EdgeEvaluation(
                    order=len(evaluations) + 1,
                    source=edge.source,
                    target=edge.target,
                    kind=edge_kind(stages[edge.source].position, stages[edge.target].position),
                    base_probability=float(edge.probability),
                    target_coverage=target_coverage,
                    effective_probability=effective,
                    threshold=float(threshold),
                    outcome=outcome,
                    target_already_compromised=already,
                    controls=controls_by_stage.get(edge.target, ()),
                )
            )

    likelihoods = _path_likelihoods(stages, entry, entry_likelihood, evaluations)
    for evaluation in evaluations:
        evaluation.transmitted_likelihood = likelihoods[evaluation.source] * evaluation.effective_probability / 100

    states = {}
    for key in stages:
        incoming = [e for e in evaluations if e.target == key]
        if key == entry:
            states[key] = STATE_ENTRY
        elif key in compromised:
            states[key] = STATE_COMPROMISED
        elif any(e.outcome == OUTCOME_BLOCKED for e in incoming):
            states[key] = STATE_BLOCKED
        elif incoming:
            states[key] = STATE_EXPOSED
        else:
            states[key] = STATE_UNAFFECTED
        if key not in compromised:
            # A stage that was attempted but not compromised keeps the
            # likelihood of its strongest failed attempt (its residual exposure).
            likelihoods[key] = max((e.transmitted_likelihood for e in incoming), default=0.0)

    return TraversalResult(states=states, likelihoods=likelihoods, evaluations=evaluations)


def _path_likelihoods(stages, entry, entry_likelihood, evaluations):
    """Max-product path likelihood over successful edges (Dijkstra variant).

    Probabilities are <= 1, so a longer path can never increase likelihood;
    this makes the search well defined even when the graph has cycles.
    """
    successful = defaultdict(list)
    for evaluation in evaluations:
        if evaluation.outcome == OUTCOME_PROPAGATED:
            successful[evaluation.source].append(evaluation)

    likelihoods = {key: 0.0 for key in stages}
    likelihoods[entry] = entry_likelihood
    heap = [(-entry_likelihood, stages[entry].position, entry)]
    settled = set()
    while heap:
        _, _, key = heapq.heappop(heap)
        if key in settled:
            continue
        settled.add(key)
        for evaluation in successful.get(key, ()):
            candidate = likelihoods[key] * evaluation.effective_probability / 100
            if evaluation.target not in settled and candidate > likelihoods[evaluation.target]:
                likelihoods[evaluation.target] = candidate
                heapq.heappush(heap, (-candidate, stages[evaluation.target].position, evaluation.target))
    return likelihoods
