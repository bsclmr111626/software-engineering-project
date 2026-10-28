"""Helpers that build engine inputs without touching the database."""

from simulation.domain import Control, Edge, SimulationInput, Stage

STAGES = (
    Stage("ide", "IDE", 1, 1),
    Stage("vcs", "Version Control", 2, 2),
    Stage("cicd", "CI/CD", 3, 2),
    Stage("registry", "Registry", 4, 2),
    Stage("production", "Production", 5, 3),
)


def chain_edges(probability=80.0):
    keys = [s.key for s in STAGES]
    return tuple(Edge(a, b, probability) for a, b in zip(keys, keys[1:], strict=False))


def make_input(**overrides):
    values = {
        "stages": STAGES,
        "entry_stage": "ide",
        "likelihood": 80.0,
        "severity": 5,
        "impact": 5,
        "edges": chain_edges(),
        "controls": (),
        "threshold": 50.0,
    }
    values.update(overrides)
    return SimulationInput(**values)


def control(key="ctl", effectiveness=50.0, stages=("vcs",), category="preventive", **extra):
    return Control(
        key=key, name=key.upper(), effectiveness=effectiveness, stages=frozenset(stages), category=category, **extra
    )
