"""Convert engine inputs and results to JSON-safe dictionaries.

These dictionaries are stored on ``SimulationRun`` so a historical report can
be rendered exactly as it was produced, even if the scenario changes later.
"""

from dataclasses import asdict, is_dataclass


def to_jsonable(value):
    if is_dataclass(value) and not isinstance(value, type):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (frozenset, set)):
        return sorted(to_jsonable(v) for v in value)
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    return value


def input_to_dict(inp):
    return to_jsonable(inp)


def result_to_dict(result, recommendations=(), contributions=()):
    data = to_jsonable(result)
    data["recommendations"] = to_jsonable(list(recommendations))
    data["control_contributions"] = to_jsonable(list(contributions))
    return data
