"""Geometry for the inline SVG charts.

Templates draw only what these functions compute (like simulation/visual.py
for the pipeline). The SVG takes its colours from CSS classes that use the
design tokens, so charts follow the theme with no re-render, and every chart
is paired with a data table in the template so no value depends on seeing it.
Scores are on CodeGuard's fixed 0-100 scale, so axes never rescale per page.
"""

from simulation.risk import RISK_BANDS

GUIDES = tuple(int(lower) for lower, _label in RISK_BANDS if lower > 0)  # 15, 30, 50


def _scale(value, domain_max, length):
    if not domain_max:
        return 0.0
    return max(0.0, min(1.0, float(value) / float(domain_max))) * length


def hbars(rows, *, max_value=100, width=640, row_height=34, bar=14, label_width=0, value_width=56):
    """Horizontal bars, one per row: {"label", "value", "cls", "tip"}.

    Bars grow from a shared baseline; values sit at the bar tip in text ink.
    """
    plot = width - label_width - value_width
    out = []
    for index, row in enumerate(rows):
        y = index * row_height + (row_height - bar) / 2
        length = round(_scale(row["value"] or 0, max_value, plot), 1)
        out.append(
            {
                **row,
                "x": label_width,
                "y": round(y, 1),
                "w": max(length, 2.0) if row["value"] else 0,
                "h": bar,
                "text_x": round(label_width + length + 8, 1),
                "text_y": round(y + bar / 2 + 4.5, 1),
                "hit_y": index * row_height,
            }
        )
    return {"width": width, "height": max(len(rows), 1) * row_height, "rows": out, "row_height": row_height}


def line_chart(
    series, labels, *, width=760, height=280, y_max=100, pad_left=40, pad_right=16, pad_top=14, pad_bottom=34
):
    """Lines over ordered categories (runs, oldest first) on a 0-y_max axis.

    series: [{"name", "cls", "values": [float|None, ...]}]
    """
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    count = len(labels)
    step = plot_w / (count - 1) if count > 1 else 0

    def x_at(i):
        return round(pad_left + (i * step if count > 1 else plot_w / 2), 1)

    def y_at(v):
        return round(pad_top + plot_h - _scale(v, y_max, plot_h), 1)

    drawn = []
    for s in series:
        points = [(x_at(i), y_at(v), v, labels[i]) for i, v in enumerate(s["values"]) if v is not None]
        path = " ".join(f"{'M' if k == 0 else 'L'} {x} {y}" for k, (x, y, _v, _l) in enumerate(points))
        drawn.append({**s, "path": path, "points": [{"x": x, "y": y, "v": v, "label": lab} for x, y, v, lab in points]})

    ticks = [{"v": v, "y": y_at(v)} for v in (0, 25, 50, 75, 100) if v <= y_max]
    guides = [{"v": v, "y": y_at(v)} for v in GUIDES]
    columns = [
        {
            "x": x_at(i),
            "label": labels[i],
            "left": round(x_at(i) - (step / 2 if step else plot_w / 2), 1),
            "w": round(step or plot_w, 1),
        }
        for i in range(count)
    ]
    # Show at most ~8 x labels so they never collide.
    every = max(1, -(-count // 8))
    for i, column in enumerate(columns):
        # The last column is labelled too, unless that would crowd the previous label.
        column["show_label"] = i % every == 0 or (i == count - 1 and i % every >= every / 2)
    return {
        "width": width,
        "height": height,
        "series": drawn,
        "ticks": ticks,
        "guides": guides,
        "columns": columns,
        "plot_left": pad_left,
        "plot_right": width - pad_right,
        "plot_top": pad_top,
        "plot_bottom": pad_top + plot_h,
        "plot_height": plot_h,
        "label_y": height - 10,
    }


def paired_columns(
    groups, *, width=760, height=280, y_max=100, pad_left=40, pad_right=16, pad_top=14, pad_bottom=40, column=18, gap=2
):
    """Two columns per group (e.g. inherent then residual risk per stage).

    groups: [{"label", "a", "b", "a_cls", "b_cls", "tip"}]
    """
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom
    band = plot_w / max(len(groups), 1)
    baseline = pad_top + plot_h
    out = []
    for i, g in enumerate(groups):
        center = pad_left + band * (i + 0.5)
        ha = round(_scale(g["a"] or 0, y_max, plot_h), 1)
        hb = round(_scale(g["b"] or 0, y_max, plot_h), 1)
        out.append(
            {
                **g,
                "ax": round(center - column - gap / 2, 1),
                "bx": round(center + gap / 2, 1),
                "ay": round(baseline - ha, 1),
                "by": round(baseline - hb, 1),
                "ah": ha,
                "bh": hb,
                "cx": round(center, 1),
                "band_x": round(pad_left + band * i, 1),
                "band_w": round(band, 1),
            }
        )
    ticks = [{"v": v, "y": round(baseline - _scale(v, y_max, plot_h), 1)} for v in (0, 25, 50, 75, 100) if v <= y_max]
    return {
        "width": width,
        "height": height,
        "groups": out,
        "column": column,
        "ticks": ticks,
        "plot_left": pad_left,
        "plot_right": width - pad_right,
        "plot_top": pad_top,
        "baseline": baseline,
        "plot_height": plot_h,
        "label_y": height - 14,
    }
