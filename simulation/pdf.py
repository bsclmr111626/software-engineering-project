"""The simulation report as a downloadable PDF (A4).

Drawn with Matplotlib, which CodeGuard already uses for charts, so no extra
system libraries are needed on the server. Text stays real text (TrueType
fonts are embedded), so the PDF can be searched, copied and read aloud, and
the stage chart is vector, not a picture.

The layout is a small flowing engine: ``_Doc`` keeps a cursor down the page,
starts a new page when the next block will not fit, and adds the running
footer ("page N of M") once every page exists. Colours come from the light
theme palette in charts.py, which core/tests/test_design.py keeps in step
with the CSS tokens.
"""

import io
import textwrap
from datetime import UTC, datetime

import matplotlib

matplotlib.use("Agg")

from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from .charts import DEFAULT_PALETTE, draw_stage_risk  # noqa: E402
from .engine import LIMITATIONS, STATE_LABELS  # noqa: E402
from .services import OUTCOME_LABELS  # noqa: E402

PAGE_W, PAGE_H = 8.27, 11.69  # A4 in inches
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 0.8, 0.85, 0.95
CONTENT_W = PAGE_W - 2 * MARGIN_X
PT = 1 / 72  # one point in inches
# DejaVu Sans averages about 0.5 em per character: enough to wrap text
# without measuring every line.
CHAR_EM = 0.5

DISCLAIMER = (
    "CodeGuard is a risk model. Scenarios are hypothetical, control effectiveness values are "
    "illustrative, and modeled improvements do not guarantee equivalent protection in a real organization."
)


def _wrap(text, width_in, size):
    chars = max(8, int((width_in - 0.1) / (CHAR_EM * size * PT)))
    lines = []
    for paragraph in str(text).splitlines() or [""]:
        lines.extend(textwrap.wrap(paragraph, chars, break_long_words=True) or [""])
    return lines


class _Doc:
    def __init__(self, palette):
        self.palette = palette
        self.pages = []
        self.fig = None
        self.y = 0.0  # inches from the top of the page
        self._new_page()

    # Pages --------------------------------------------------------------

    def _new_page(self):
        fig = Figure(figsize=(PAGE_W, PAGE_H), facecolor="none")
        self.pages.append(fig)
        self.fig = fig
        self.y = MARGIN_TOP

    def ensure(self, height):
        if self.y + height > PAGE_H - MARGIN_BOTTOM:
            self._new_page()

    def gap(self, height):
        self.y += height

    def _text(self, x, y, text, size, color=None, weight="normal", **kwargs):
        self.fig.text(
            x / PAGE_W,
            1 - y / PAGE_H,
            text,
            fontsize=size,
            color=color or self.palette.ink,
            fontweight=weight,
            va="top",
            ha=kwargs.pop("ha", "left"),
            **kwargs,
        )

    def rule(self, color=None, width=0.6):
        self.fig.add_artist(
            Line2D(
                [MARGIN_X / PAGE_W, (PAGE_W - MARGIN_X) / PAGE_W],
                [1 - self.y / PAGE_H] * 2,
                color=color or self.palette.grid,
                linewidth=width,
            )
        )

    # Blocks ---------------------------------------------------------------

    def kicker(self, text):
        self._text(MARGIN_X, self.y, text.upper(), 8, self.palette.muted, family="monospace")
        self.y += 0.28

    def title(self, text):
        for line in _wrap(text, CONTENT_W, 22):
            self.ensure(0.42)
            self._text(MARGIN_X, self.y, line, 22, weight="bold")
            self.y += 0.4
        self.y += 0.1

    def heading(self, text, keep=1.3):
        # ``keep``: room for the start of what follows, so a heading never
        # sits alone at the bottom of a page.
        self.ensure(0.66 + keep)
        self.y += 0.22
        self._text(MARGIN_X, self.y, text, 13.5, weight="bold")
        self.y += 0.3
        self.rule()
        self.y += 0.14

    def subheading(self, text, aside=None):
        self.ensure(0.4)
        self._text(MARGIN_X, self.y, text, 10.5, weight="bold")
        if aside:
            self._text(PAGE_W - MARGIN_X, self.y, aside, 9.5, self.palette.severity["low"], weight="bold", ha="right")
        self.y += 0.24

    def paragraph(self, text, size=9.5, color=None, indent=0.0, bullet=None):
        line_h = size * 1.45 * PT
        lines = _wrap(text, CONTENT_W - indent, size)
        if len(lines) <= 5:  # short paragraphs are never split across pages
            self.ensure(line_h * len(lines))
        for i, line in enumerate(lines):
            self.ensure(line_h)
            if bullet and i == 0:
                self._text(MARGIN_X + indent - 0.2, self.y, bullet, size, color or self.palette.muted)
            self._text(MARGIN_X + indent, self.y, line, size, color)
            self.y += line_h
        self.y += size * 0.5 * PT

    def ledger(self, rows, label_w=1.6, size=9):
        line_h = size * 1.45 * PT
        for label, value in rows:
            lines = _wrap(value, CONTENT_W - label_w, size)
            self.ensure(line_h * len(lines) + 0.06)
            self._text(MARGIN_X, self.y, label, size, self.palette.muted)
            for i, line in enumerate(lines):
                self._text(MARGIN_X + label_w, self.y + i * line_h, line, size)
            self.y += line_h * len(lines) + 0.06

    def metrics(self, items):
        """A row of headline numbers: (label, value, colour or None, note)."""
        height = 0.95
        self.ensure(height)
        width = CONTENT_W / len(items)
        top = self.y
        self.rule(self.palette.guide, 0.8)
        for i, (label, value, color, note) in enumerate(items):
            x = MARGIN_X + i * width
            self._text(x, top + 0.12, label, 8, self.palette.muted)
            self._text(x, top + 0.32, value, 20, color, weight="bold")
            if note:
                self._text(x, top + 0.7, note, 8, color or self.palette.muted)
        self.y = top + height
        self.rule(self.palette.guide, 0.8)
        self.y += 0.15

    def table(self, header, rows, widths, size=8.5, numeric=()):
        """A table whose cells wrap; the header repeats on every new page."""
        scale = CONTENT_W / sum(widths)
        widths = [w * scale for w in widths]
        line_h = size * 1.4 * PT
        pad = 0.07

        def draw_row(cells, bold=False, color=None):
            wrapped = [_wrap(c, w - 0.12, size) for c, w in zip(cells, widths, strict=True)]
            height = max(len(w) for w in wrapped) * line_h + 2 * pad
            x = MARGIN_X
            for col, (lines, w) in enumerate(zip(wrapped, widths, strict=True)):
                for i, line in enumerate(lines):
                    if col in numeric:
                        self._text(x + w - 0.1, self.y + pad + i * line_h, line, size, color, ha="right")
                    else:
                        self._text(x, self.y + pad + i * line_h, line, size, color, weight="bold" if bold else "normal")
                    if col in numeric and bold:
                        self.fig.texts[-1].set_fontweight("bold")
                x += w
            self.y += height
            self.rule()
            return height

        def header_row():
            draw_row(header, bold=True, color=self.palette.muted)

        self.ensure(4 * line_h + 4 * pad)
        header_row()
        for row in rows:
            needed = max(len(_wrap(c, w - 0.12, size)) for c, w in zip(row, widths, strict=True)) * line_h + 2 * pad
            if self.y + needed > PAGE_H - MARGIN_BOTTOM:
                self._new_page()
                header_row()
            draw_row(row)
        self.y += 0.15

    def chart(self, draw, height=3.4, below=0.65):
        """Draws a chart in a box ``height`` inches tall; ``below`` leaves room
        for wrapped axis labels under the plot."""
        self.ensure(height + below)
        left = MARGIN_X + 0.55
        ax = self.fig.add_axes(
            (
                left / PAGE_W,
                1 - (self.y + height) / PAGE_H,
                (PAGE_W - MARGIN_X - left) / PAGE_W,
                (height - 0.45) / PAGE_H,
            )
        )
        draw(ax)
        self.y += height + below

    # Output -----------------------------------------------------------------

    def finish(self, footer_left, metadata):
        total = len(self.pages)
        for number, fig in enumerate(self.pages, start=1):
            self.fig = fig
            y = PAGE_H - MARGIN_BOTTOM + 0.35
            fig.add_artist(
                Line2D(
                    [MARGIN_X / PAGE_W, (PAGE_W - MARGIN_X) / PAGE_W],
                    [1 - (y - 0.1) / PAGE_H] * 2,
                    color=self.palette.grid,
                    linewidth=0.6,
                )
            )
            self._text(MARGIN_X, y, footer_left, 7.5, self.palette.muted)
            self._text(PAGE_W - MARGIN_X, y, f"Page {number} of {total}", 7.5, self.palette.muted, ha="right")
        buffer = io.BytesIO()
        with matplotlib.rc_context({"pdf.fonttype": 42, "font.family": "DejaVu Sans"}):
            with PdfPages(buffer, metadata=metadata) as pdf:
                for fig in self.pages:
                    pdf.savefig(fig, facecolor="white")
        return buffer.getvalue()


def _fmt(value, suffix=""):
    return "—" if value is None else f"{value:g}{suffix}"


def render_report(run, *, generated_for, workspace_name="", palette=DEFAULT_PALETTE):
    """The PDF bytes for ``run``. ``generated_for`` is the username in the footer."""
    doc = _Doc(palette)
    stage_results = list(run.stage_results.all())
    events = list(run.events.all())
    result = run.result or {}
    completed = run.status == "completed"
    controls = run.input_snapshot.get("input", {}).get("controls", []) if run.input_snapshot else []

    doc.kicker(f"CodeGuard simulation report · run {run.short_id}")
    doc.title(run.scenario_name)
    doc.ledger(
        [
            ("Executed", f"{run.created_at:%Y-%m-%d %H:%M} UTC by {run.user.get_username()}"),
            *([("Workspace", workspace_name)] if workspace_name else []),
            ("Status", run.get_status_display() + (" · shared with the workspace" if run.is_shared else "")),
            ("Scenario version", str(run.scenario_version)),
            ("Entry point", run.entry_stage_name),
        ]
    )
    doc.gap(0.15)

    if completed:
        severity = palette.severity.get(run.classification, palette.ink)
        doc.metrics(
            [
                ("Residual risk", _fmt(run.residual_risk), severity, run.classification.title()),
                ("Inherent risk", _fmt(run.inherent_risk), None, "No controls"),
                ("Modeled reduction", _fmt(run.risk_reduction), None, "points"),
                ("Stages compromised", f"{run.compromised_count} of {len(stage_results)}", None, None),
            ]
        )

    doc.heading("1. Summary")
    if completed:
        doc.paragraph(
            f"With the enabled controls, the overall residual risk is {_fmt(run.residual_risk)} "
            f"({run.classification}), compared with an inherent risk of {_fmt(run.inherent_risk)} "
            f"({result.get('inherent_classification', '—')}) with no controls: a modeled reduction of "
            f"{_fmt(run.risk_reduction)} points. {run.compromised_count} of {len(stage_results)} stages were "
            f"compromised ({result.get('inherent_compromised_count', '—')} without controls)."
        )
        for i, line in enumerate(result.get("explanation", []), start=1):
            doc.paragraph(line, size=9, indent=0.3, bullet=f"{i}.")
    else:
        doc.paragraph(
            f"This simulation did not complete: {run.error_message or 'the run is still pending'}. "
            "No partial results were saved."
        )

    number = 2
    if completed:
        doc.heading(f"{number}. Risk by stage", keep=4.1)
        doc.chart(lambda ax: draw_stage_risk(ax, stage_results, palette))
        doc.table(
            ["Stage", "State", "Inherent", "Residual", "Explanation"],
            [
                [
                    s.stage_name,
                    STATE_LABELS.get(s.state, s.state),
                    _fmt(s.inherent_risk),
                    _fmt(s.residual_risk),
                    s.explanation,
                ]
                for s in stage_results
            ],
            widths=[1.3, 1.0, 0.7, 0.7, 3.0],
            numeric=(2, 3),
        )
        number += 1

        doc.heading(f"{number}. Paths evaluated")
        if events:
            doc.table(
                ["#", "Path", "Base", "Effective", "Outcome"],
                [
                    [
                        str(e.order),
                        f"{e.source_name} → {e.target_name}",
                        _fmt(e.base_probability, "%"),
                        _fmt(e.effective_probability, "%"),
                        OUTCOME_LABELS.get(e.outcome, e.outcome),
                    ]
                    for e in events
                ],
                widths=[0.35, 3.2, 0.8, 0.9, 1.5],
                numeric=(2, 3),
            )
        else:
            doc.paragraph("No propagation rules from the entry stage.")
        number += 1

        doc.heading(f"{number}. Recommendations")
        recommendations = result.get("recommendations", [])
        for i, rec in enumerate(recommendations, start=1):
            doc.subheading(f"{i}. {rec['name']}", aside=f"−{rec['risk_reduction']:g}")
            doc.paragraph(rec.get("reason", ""), size=9)
            doc.paragraph(
                f"{rec.get('category', '').title()} · {rec.get('effort', '').title()} effort · "
                f"{rec.get('priority', '').title()} priority",
                size=8,
                color=palette.muted,
            )
        if not recommendations:
            doc.paragraph("No catalog control would further reduce the modeled risk for this configuration.")
        number += 1

    doc.heading(f"{number}. Inputs and limitations")
    doc.ledger(
        [
            ("Base likelihood", _fmt(run.likelihood, "%")),
            ("Severity / impact", f"{_fmt(run.severity)} / {_fmt(run.impact)}"),
            ("Threshold", _fmt(run.threshold, "%")),
            ("Enabled controls", ", ".join(c.get("name", c.get("slug", "")) for c in controls) or "None"),
            ("Model version", str(result.get("model_version") or "—")),
        ]
    )
    doc.gap(0.1)
    doc.subheading("Limitations")
    for item in [*(result.get("limitations") or LIMITATIONS), DISCLAIMER]:
        doc.paragraph(item, size=8.5, indent=0.25, bullet="•")

    now = datetime.now(UTC)
    return doc.finish(
        f"CodeGuard · run {run.short_id} · generated {now:%Y-%m-%d %H:%M} UTC for {generated_for}",
        {
            "Title": f"CodeGuard report: {run.scenario_name}",
            "Author": "CodeGuard",
            "Subject": f"Simulation run {run.id}",
            "Creator": "CodeGuard",
            "CreationDate": now,
        },
    )
