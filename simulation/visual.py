"""Geometry for the five-stage pipeline SVG.

The template ``components/pipeline.html`` only draws what this module
computes, keeping layout logic out of templates and easy to test.
"""

from .propagation import KIND_BYPASS, KIND_FORWARD, KIND_REVERSE, edge_kind

WIDTH = 1000
HEIGHT = 300
NODE_W = 150
NODE_H = 96
NODE_TOP = (HEIGHT - NODE_H) // 2

STATE_SYMBOLS = {
    "entry": ("▶", "Entry point"),
    "compromised": ("✖", "Compromised"),
    "blocked": ("⊘", "Blocked"),
    "exposed": ("△", "Exposed"),
    "unaffected": ("✓", "Unaffected"),
    "rule": ("", ""),
}

EDGE_LABELS = {
    "propagated": "Propagated",
    "blocked_by_controls": "Blocked by controls",
    "below_threshold": "Below threshold",
    "rule": "Configured rule",
    "not_evaluated": "Not evaluated (source not compromised)",
}


def build_pipeline(stages, edges):
    """Return SVG node and edge geometry.

    stages -- list of dicts: key, name, position, state (optional), risk (optional)
    edges  -- list of dicts: source, target, status, label
    """
    ordered = sorted(stages, key=lambda s: s["position"])
    spacing = WIDTH / max(len(ordered), 1)
    centers, positions, names, nodes = {}, {}, {}, []
    for index, stage in enumerate(ordered):
        cx = spacing * (index + 0.5)
        centers[stage["key"]] = cx
        names[stage["key"]] = stage["name"]
        positions[stage["key"]] = stage["position"]
        state = stage.get("state", "rule")
        symbol, state_label = STATE_SYMBOLS.get(state, ("", ""))
        nodes.append(
            {
                **stage,
                "risk": stage.get("risk"),
                "state": state,
                "symbol": symbol,
                "state_label": state_label,
                "x": round(cx - NODE_W / 2, 1),
                "y": NODE_TOP,
                "cx": round(cx, 1),
                "w": NODE_W,
                "h": NODE_H,
                "name_lines": _wrap(stage["name"]),
            }
        )

    drawn = []
    for edge in edges:
        if edge["source"] not in centers or edge["target"] not in centers:
            continue
        sx, tx = centers[edge["source"]], centers[edge["target"]]
        kind = edge_kind(positions[edge["source"]], positions[edge["target"]])
        span = abs(positions[edge["target"]] - positions[edge["source"]])
        if kind == KIND_FORWARD:
            y = NODE_TOP + NODE_H / 2
            path = f"M {sx + NODE_W / 2:.1f} {y} L {tx - NODE_W / 2 - 4:.1f} {y}"
            label_x, label_y = (sx + tx) / 2, y - 8
        else:
            above = kind == KIND_BYPASS
            base_y = NODE_TOP if above else NODE_TOP + NODE_H
            bend = 34 + 12 * span
            control_y = base_y - bend if above else base_y + bend
            offset = 22 if sx < tx else -22
            x1, x2 = sx + offset, tx - offset
            path = f"M {x1:.1f} {base_y} Q {(x1 + x2) / 2:.1f} {control_y} {x2:.1f} {base_y + (-4 if above else 4)}"
            label_x = (x1 + x2) / 2
            label_y = (2 * base_y + 2 * control_y) / 4 + (-4 if above else 12)
        drawn.append(
            {
                **edge,
                "source_name": names[edge["source"]],
                "target_name": names[edge["target"]],
                "kind": kind,
                "path": path,
                "label_x": round(label_x, 1),
                "label_y": round(label_y, 1),
                "status_label": EDGE_LABELS.get(edge["status"], edge["status"]),
            }
        )
    return {
        "width": WIDTH,
        "height": HEIGHT,
        "nodes": nodes,
        "edges": drawn,
        "kinds": (KIND_FORWARD, KIND_BYPASS, KIND_REVERSE),
    }


def _wrap(name, limit=16):
    words, lines, current = name.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > limit and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:2]
