"""Server-side Matplotlib charts rendered from stored simulation results.

Charts are rendered in memory to PNG bytes and returned by access-controlled
views, so no files are written to disk and no file path is ever exposed.
The object-oriented API (Figure + FigureCanvasAgg) is used instead of pyplot:
it keeps no global state, is safe in a multi-threaded server and needs no
explicit ``close()``.

Colours come from the page's CSS tokens: static/js/app.js reads them with
getComputedStyle and passes them as ``?palette=`` (see ``parse_palette``), so
charts follow the active theme. Without JavaScript, or with a missing or
invalid palette, the light theme is used.
"""

import io
import re
import textwrap
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")  # non-interactive backend suitable for servers

from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.legend_handler import HandlerTuple  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from .risk import RISK_BANDS, classify  # noqa: E402

# CSS tokens a chart needs, in the order they appear in ?palette=.
PALETTE_TOKENS = (
    "surface",
    "text",
    "text-muted",
    "border",
    "border-strong",
    "sev-low",
    "sev-med",
    "sev-high",
    "sev-crit",
)
_HEX = re.compile(r"^#?([0-9A-Fa-f]{6})$")


@dataclass(frozen=True)
class Palette:
    surface: str  # --surface: charts sit on cards
    ink: str  # --text
    muted: str  # --text-muted: neutral series (inherent / before) and axis labels
    grid: str  # --border
    guide: str  # --border-strong
    severity: dict  # --sev-low / -med / -high / -crit keyed by risk class

    @property
    def outcomes(self):
        return {
            "propagated": self.severity["critical"],
            "blocked_by_controls": self.severity["low"],
            "below_threshold": self.muted,
        }

    @property
    def query(self):
        """This palette in the ?palette= format (hex without '#', token order)."""
        values = [self.surface, self.ink, self.muted, self.grid, self.guide, *self.severity.values()]
        return ",".join(value.lstrip("#") for value in values)


def _palette(values):
    surface, ink, muted, grid, guide, low, med, high, crit = values
    return Palette(
        surface,
        ink,
        muted,
        grid,
        guide,
        {"low": low, "moderate": med, "high": high, "critical": crit},
    )


# The light (default) theme. Mirrors the :root tokens in static/css/codeguard.css
# (core/tests/test_design.py keeps the two in sync).
DEFAULT_PALETTE = _palette(
    ["#FFFEFB", "#1A1917", "#5F5A50", "#E0D9CB", "#C4B9A4", "#2A6E45", "#855600", "#B23A1E", "#8A1538"]
)


def parse_palette(value):
    """Parse ?palette= (comma-separated hex colours in PALETTE_TOKENS order).

    Anything malformed falls back to the default palette rather than erroring,
    so a stale or hand-edited URL still renders a chart.
    """
    parts = (value or "").split(",")
    if len(parts) != len(PALETTE_TOKENS):
        return DEFAULT_PALETTE
    matches = [_HEX.match(part.strip()) for part in parts]
    if not all(matches):
        return DEFAULT_PALETTE
    return _palette(["#" + m.group(1).upper() for m in matches])


def _figure(palette, width=8.0, height=4.0):
    fig = Figure(figsize=(width, height), dpi=110, facecolor=palette.surface)
    FigureCanvasAgg(fig)
    return fig


def _style(ax, palette, title, xlabel=None, ylabel=None):
    ax.set_facecolor(palette.surface)
    ax.set_title(title, color=palette.ink, fontsize=12, loc="left", pad=12)
    if xlabel:
        ax.set_xlabel(xlabel, color=palette.muted, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=palette.muted, fontsize=9)
    ax.tick_params(colors=palette.muted, labelsize=9, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(palette.grid)


def _tick_label(name):
    return textwrap.fill(name, 14)


def _png(fig, palette):
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=palette.surface, bbox_inches="tight")
    fig.clear()
    return buffer.getvalue()


def _severity_colors(palette, values):
    """Colour each bar by the risk class of its own value."""
    return [palette.severity[classify(value or 0)] for value in values]


def _legend(ax, palette, neutral_label, classed_label):
    """Legend for a neutral series beside a series coloured by risk class.

    The classed series is shown as a strip of the four severity colours, so the
    key explains that bar colour encodes the risk class.
    """
    handles = [
        Patch(facecolor=palette.muted, edgecolor=palette.muted),
        tuple(Patch(facecolor=color, edgecolor=color) for color in palette.severity.values()),
    ]
    legend = ax.legend(
        handles,
        [neutral_label, classed_label],
        handler_map={tuple: HandlerTuple(ndivide=None, pad=0)},
        handlelength=3,
        frameon=False,
        fontsize=9,
        loc="upper right",
    )
    for text in legend.get_texts():
        text.set_color(palette.ink)


def _band_guides(ax, palette):
    """Dashed vertical guides at the classification band boundaries."""
    for lower, label in RISK_BANDS:
        if lower <= 0:
            continue
        ax.axvline(lower, color=palette.guide, linewidth=1, linestyle="--", zorder=0)
        # Label sits inside the plot, just above the x-axis, in axis-relative y.
        ax.text(
            lower + 0.8,
            0.03,
            f"{label.title()} ≥ {lower:g}",
            color=palette.muted,
            fontsize=8,
            transform=ax.get_xaxis_transform(),
        )


def overall_risk_chart(run, palette=DEFAULT_PALETTE):
    """Chart 1: overall inherent vs residual risk."""
    fig = _figure(palette, 8, 2.6)
    ax = fig.add_subplot()
    labels = ["Inherent (no controls)", "Residual (with controls)"]
    values = [run.inherent_risk or 0, run.residual_risk or 0]
    colors = [palette.muted, *_severity_colors(palette, values[1:])]
    bars = ax.barh(labels, values, color=colors, height=0.5, zorder=2)
    for bar, value in zip(bars, values, strict=False):
        ax.text(
            bar.get_width() + 1,
            bar.get_y() + bar.get_height() / 2,
            f"{value:.1f}",
            va="center",
            color=palette.ink,
            fontsize=10,
        )
    ax.set_xlim(0, 100)
    ax.invert_yaxis()
    _band_guides(ax, palette)
    _style(ax, palette, "Overall risk: inherent vs residual", xlabel="Weighted risk score (0-100)")
    return _png(fig, palette)


def stage_risk_chart(stage_results, palette=DEFAULT_PALETTE):
    """Chart 2: risk score by supply chain stage."""
    fig = _figure(palette, 8, 4)
    ax = fig.add_subplot()
    names = [_tick_label(s.stage_name) for s in stage_results]
    x = range(len(stage_results))
    width = 0.38
    ax.bar(
        [i - width / 2 for i in x],
        [s.inherent_risk for s in stage_results],
        width,
        color=palette.muted,
        zorder=2,
    )
    residual_bars = ax.bar(
        [i + width / 2 for i in x],
        [s.residual_risk for s in stage_results],
        width,
        color=_severity_colors(palette, [s.residual_risk for s in stage_results]),
        zorder=2,
    )
    for bar, stage in zip(residual_bars, stage_results, strict=False):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.5,
            f"{stage.residual_risk:.1f}",
            ha="center",
            color=palette.ink,
            fontsize=8,
        )
    ax.set_xticks(list(x), names)
    ax.set_ylim(0, 100)
    ax.yaxis.grid(True, color=palette.grid, linewidth=0.8, zorder=0)
    _style(ax, palette, "Risk score by supply chain stage", ylabel="Risk score (0-100)")
    _legend(ax, palette, "Inherent", "Residual (colour = risk class)")
    return _png(fig, palette)


def outcome_chart(events, palette=DEFAULT_PALETTE):
    """Chart 3: distribution of propagation outcomes."""
    order = [
        ("propagated", "Propagated"),
        ("blocked_by_controls", "Blocked by controls"),
        ("below_threshold", "Below threshold"),
    ]
    counts = {key: 0 for key, _ in order}
    for event in events:
        counts[event.outcome] = counts.get(event.outcome, 0) + 1
    fig = _figure(palette, 8, 2.8)
    ax = fig.add_subplot()
    labels = [label for _, label in order]
    values = [counts[key] for key, _ in order]
    bars = ax.barh(labels, values, color=[palette.outcomes[k] for k, _ in order], height=0.5, zorder=2)
    for bar, value in zip(bars, values, strict=False):
        ax.text(
            bar.get_width() + 0.08,
            bar.get_y() + bar.get_height() / 2,
            str(value),
            va="center",
            color=palette.ink,
            fontsize=10,
        )
    ax.set_xlim(0, max(values + [1]) + 1)
    ax.xaxis.get_major_locator().set_params(integer=True)
    ax.invert_yaxis()
    _style(ax, palette, "Propagation attempts by outcome", xlabel="Number of evaluated edges")
    return _png(fig, palette)


def comparison_chart(run_a, run_b, rows, palette=DEFAULT_PALETTE):
    """Chart 4: before/after mitigation comparison of two runs, by stage."""
    fig = _figure(palette, 8, 4)
    ax = fig.add_subplot()
    x = range(len(rows))
    width = 0.38
    ax.bar(
        [i - width / 2 for i in x],
        [r["risk_a"] for r in rows],
        width,
        color=palette.muted,
        zorder=2,
    )
    after = ax.bar(
        [i + width / 2 for i in x],
        [r["risk_b"] for r in rows],
        width,
        color=_severity_colors(palette, [r["risk_b"] for r in rows]),
        zorder=2,
    )
    for bar, row in zip(after, rows, strict=False):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.5,
            f"{row['risk_b']:.1f}",
            ha="center",
            color=palette.ink,
            fontsize=8,
        )
    names = [_tick_label(r["name"]) for r in rows]
    ax.set_xticks(list(x), names)
    ax.set_ylim(0, 100)
    ax.yaxis.grid(True, color=palette.grid, linewidth=0.8, zorder=0)
    _style(ax, palette, "Residual risk by stage: before vs after", ylabel="Residual risk (0-100)")
    _legend(
        ax,
        palette,
        f"Before: run {run_a.short_id} ({run_a.residual_risk:.1f})",
        f"After: run {run_b.short_id} ({run_b.residual_risk:.1f}, colour = risk class)",
    )
    return _png(fig, palette)


def distribution_chart(band_counts, palette=DEFAULT_PALETTE):
    """Dashboard: number of runs in each residual-risk classification band."""
    order = ["low", "moderate", "high", "critical"]
    fig = _figure(palette, 8, 3)
    ax = fig.add_subplot()
    values = [band_counts.get(b, 0) for b in order]
    colors = [palette.severity[b] for b in order]
    bars = ax.bar([b.title() for b in order], values, color=colors, width=0.55, zorder=2)
    for bar, value in zip(bars, values, strict=False):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.05,
            str(value),
            ha="center",
            va="bottom",
            color=palette.ink,
            fontsize=10,
        )
    ax.set_ylim(0, max(values + [1]) * 1.25)
    ax.yaxis.get_major_locator().set_params(integer=True)
    ax.yaxis.grid(True, color=palette.grid, linewidth=0.8, zorder=0)
    _style(ax, palette, "Simulation runs by residual risk class", ylabel="Runs")
    return _png(fig, palette)
