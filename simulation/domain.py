"""Plain data types used by the simulation engine.

These classes deliberately have no Django dependency. The engine works on
these immutable values, which keeps it easy to unit test and guarantees that
a simulation cannot accidentally read or write the database.
"""

from dataclasses import dataclass, field

# How a security control influences the model.
#   PREVENT  - reduces the probability that an attack enters a protected stage
#              (preventive controls such as MFA or signed artifacts).
#   MITIGATE - does not stop propagation, but reduces the residual risk of a
#              stage that is reached (detective and recovery controls).
MODE_PREVENT = "prevent"
MODE_MITIGATE = "mitigate"

CATEGORY_MODES = {
    "preventive": MODE_PREVENT,
    "detective": MODE_MITIGATE,
    "recovery": MODE_MITIGATE,
}


@dataclass(frozen=True)
class Stage:
    """One of the ordered supply chain stages (a node in the graph)."""

    key: str
    name: str
    position: int
    weight: int = 1  # criticality weight used when aggregating overall risk


@dataclass(frozen=True)
class Edge:
    """A directed propagation relationship between two stages."""

    source: str
    target: str
    probability: float  # 0-100: chance the compromise crosses this edge
    rationale: str = ""


@dataclass(frozen=True)
class Control:
    """A security control that is enabled for a simulation run."""

    key: str
    name: str
    effectiveness: float  # 0-100, illustrative model parameter
    stages: frozenset = field(default_factory=frozenset)
    category: str = "preventive"
    effort: str = "medium"
    priority: str = "medium"
    addresses: str = ""

    @property
    def mode(self):
        return CATEGORY_MODES.get(self.category, MODE_PREVENT)


@dataclass(frozen=True)
class SimulationInput:
    """Everything the engine needs to run one deterministic simulation."""

    stages: tuple
    entry_stage: str
    likelihood: float  # 0-100 base likelihood of the initial compromise
    severity: int  # 1-5
    impact: int  # 1-5
    edges: tuple = ()
    controls: tuple = ()
    threshold: float = 50.0  # edges propagate when effective probability >= threshold
