# CodeGuard design system

## Brand

**Personality:** field notes for the software supply chain. Calm, precise and evidence-led. CodeGuard
reads like a well-made engineering report, not a hacker console: warm paper, graphite ink and one
signal colour. It never dramatises risk; it shows its working.

**Mark:** a graphite tile holding a dependency path that runs from a source node, branches once, and
ends at a signal node in the accent colour (`templates/partials/logo.html`). The wordmark is
"CodeGuard" in Instrument Sans, semibold, tight tracking. Never recolour the mark outside the tokens.

**Motifs:** nodes and edges (dependency graphs), the dot-grid "paper" behind diagrams, numbered
steps in monospace, hairline rules. Illustrations are original inline SVG (`templates/illustrations/`)
drawn only with the `.illo .i-*` classes, so they follow the theme. No stock photography, padlocks,
hoodies or glowing circuitry.

## Colour

Colours are defined **only** between the `@tokens:start` and `@tokens:end` markers at the top of
`static/css/codeguard.css`. Components, templates and JavaScript use the variables and never branch on
the theme (no `[data-theme]` selectors, no `prefers-color-scheme` queries, no theme checks in JS).
`core/tests/test_design.py` enforces this.

| Role | Token | Light | Dark | Used for |
|---|---|---|---|---|
| Paper | `--bg` | #F4F1EA | #131210 | page background |
| Surface | `--surface`, `--surface-raised` | #FFFEFB | #1B1A17 | panels, cards, menus |
| Sunken | `--surface-sunken` | #ECE7DC | #0E0D0B | sidebar, wells, tracks |
| Ink | `--text` | #1A1917 | #EFEAE0 | text, the logo tile |
| Secondary ink | `--text-muted` | #5F5A50 | #A69E90 | secondary text, control outlines |
| Hairlines | `--border`, `--border-strong` | | | dividers; never a control boundary on its own |
| Signal (accent) | `--accent`, `--accent-hover`, `--accent-soft`, `--on-accent` | Ultramarine #2F3E9E | #9EA8F5 | interaction only: primary buttons, links, focus rings, the active nav item, selected options, the residual-risk series |
| Ink band | `--ink-band`, `--on-ink-band`, `--on-ink-muted` | | | dark editorial bands on the landing and auth pages |
| Risk | `--sev-low/-med/-high/-crit` and `-bg` | green, ochre, vermilion, crimson | | risk classes and stage states **only** |

Rules:

- The accent means "you can act here" or "this is selected". It never shows a risk level.
- Risk colours are reserved for risk: Low, Moderate, High, Critical, and the stage states that are
  risk outcomes (entry and compromised = high/critical, exposed = moderate, blocked = low). Every use
  is paired with an icon and a text label, so meaning never depends on colour.
- Surfaces (Settings > Appearance): **Paper** (default, the table above), **Pearl** or **Sage**. Each
  variant is a light-theme token block that keeps ink, accent and risk colours and only changes
  surfaces, hairlines and secondary ink. **Pearl** is cool and crisp: `--bg` #F5F6F8,
  `--surface`/`--surface-raised` #FFFFFF, `--surface-sunken` #ECEEF2, `--border` #E1E4E9,
  `--border-strong` #C3C8D0, and a cool secondary ink `--text-muted` #585C64. **Sage** is Pearl with a faint green-grey cast:
  `--bg` #F4F6F3, `--surface-sunken` #EBEEEA, `--border` #DFE4DE, `--border-strong` #C1C9C0,
  `--text-muted` #565E58. Its tint is kept at about half the saturation of `--sev-low-bg` so the
  low-risk green stays distinct. The dark theme is the same for all three. (A fourth, warm-leaning
  **Neutral** surface was tried and retired on 2026-10-28 as too close to Paper and Pearl; anyone who
  had chosen it was moved to Paper.)
- Accent themes (Settings > Appearance: Ultramarine, Iris, Graphite) and increased contrast
  (Settings > Accessibility) are token blocks too. They may only override existing tokens.
- All text pairs meet WCAG AA in both themes, including each risk colour on its own tint.
- Shadows: only `var(--shadow-overlay)` on menus and tooltips, and blur-free hairline/inset rings.
  The only gradient is the dot-grid paper texture behind diagrams (`radial-gradient` of `--border`).

## Typography

| Face | Variable | Use |
|---|---|---|
| Newsreader (serif, 400–600, italic) | `--font-display` | page titles (h1), display headings, landing bands |
| Instrument Sans (400–700) | `--font-sans` | everything else, including large figures (figures are data, not decoration) |
| JetBrains Mono (400–500) | `--font-mono` | eyebrows, table column heads, identifiers, step numbers, axis ticks |

Scale (rem): 0.75 · 0.8125 · 0.9375 (body) · 1.0625 · 1.25 · 1.5 · 2 · 2.625 · display clamp up to
4.4. Labels are sentence case; no uppercase letter-spaced labels. Settings > Text and typography
scales the root size (93.75 / 100 / 112.5 / 125 %) and can switch headings to the sans.

## Layout and spacing

- Spacing scale `--space-1` … `--space-8` (0.25rem → 4.5rem). Sections are separated by
  `--gap-section`; panels pad by `--pad-panel`; table rows by `--pad-row`. Compact density
  (Settings > Display) only changes these three plus page margins.
- Content max width 1240px with responsive page padding. Two-column layouts (`.cg-split`) collapse
  to one column below 1100px; the sidebar becomes an off-canvas drawer below 992px.
- Do not fit everything above the fold. If a page needs more, split it: tabs with their own URLs
  (`.cg-tabs`), detail pages, or a stepper.

## Application shell

- **Sidebar** (sunken paper): brand, then navigation grouped the way an analyst works —
  Overview; *Model* (Supply chain, Threat library, Security controls); *Simulate* (Simulations,
  Results); *Analyze and respond* (Risk analysis, Remediation); *Records* (Reports, Activity and
  audit); footer: Methodology, Settings. The active item has `aria-current="page"`, a 3px accent
  bar and an accent icon.
- **Top bar:** breadcrumbs (only the current page on phones), contextual "New simulation", theme
  switch, notifications (with unread count) and the account menu (profile, settings, appearance,
  security, users and roles for admins, sign out as a CSRF-protected POST).
- **Page header:** mono eyebrow with the area, serif h1, a lede, actions on the right. One h1 per
  page, and at most one primary button per view.

## Components (all in `codeguard.css`)

Panels (`.cg-panel`), metric strips (`.cg-metrics`), ledgers (`.cg-ledger`), tables (`.table`,
mono headers, hairline rows), row lists, cards for collections (`.cg-card-grid`), tabs and
segmented filters (links, so every view has a URL), filter bars, badges for risk and state, status
dots, meters (`progress.cg-meter`), choice cards and switches for settings, the stepper, timeline,
notices, empty states with an illustration, and the pipeline diagram.

## Charts

- Inline SVG charts (`core/svgcharts.py` computes geometry; templates draw it) use the tokens
  directly, so they follow the theme without a re-render. Server-drawn Matplotlib charts read the
  tokens through `?palette=` (see `static/js/app.js`).
- Bars and segments that show a risk class use the risk colours. Inherent vs residual uses
  `--border-strong`/dashed muted (inherent) against the accent (residual). Single-series charts use
  one colour and no legend box.
- Every chart has: a `role="img"` with a title and a description containing the numbers, a
  keyboard-focusable hover/focus tooltip per mark, and a "Show as a table" disclosure. Gridlines are
  hairlines; class boundaries (15, 30, 50) are dashed guides.

## Accessibility

Keyboard reachable everywhere with a visible 2px accent focus ring; skip link; landmarks; one h1;
labelled forms with linked errors; tables named with `aria-label` (not hidden captions); reduced
motion honoured from the OS or the setting; reflow without horizontal scrolling at 390px. Verified
with `tools/a11y` (axe-core, keyboard, reflow) in both themes.
