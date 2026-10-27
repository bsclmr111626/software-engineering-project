# CodeGuard design rules

Light, paper-like theme. It should feel like a governance report, not a hacker console.

- Use only the CSS variables defined in :root. No hardcoded hex values in components.
- Page background is var(--bg). Cards are var(--surface) with a 1px var(--border) hairline. No shadows.
- Text is var(--text); secondary text is var(--text-muted).
- One accent (var(--accent)) per screen: the primary button and the active nav item only.
- Risk colors are reserved for risk. Low, Medium, High and Critical use the --sev-* pairs
  (text color on its matching -bg tint). Never use the accent to show a risk level.
- Charts: color bars and segments by risk class using the --sev-* colors.
  Use var(--text-muted) for neutral series. Never use default chart greens or blues.
- Sidebar: var(--surface-sunken) background, not dark.
- Section labels in sentence case, regular weight. No uppercase letter-spaced labels.
- Forbidden: navy or slate-900 backgrounds, teal or cyan accents, gradients, glows.
- Headings and big numbers can use a serif (Source Serif 4, loaded from Google Fonts) to keep the report feel.
  Everything else is a clean sans-serif.

## Dark mode

- Both themes share the same token names. The light values are the default `:root` block;
  the dark values live only in the `[data-theme="dark"]` block. Nothing else defines a color.
- Components must never branch on the theme: no `[data-theme]` selectors, no
  `prefers-color-scheme` queries and no theme checks in component CSS or JavaScript.
  They only use the variables, so they adapt automatically.
- The theme is set on `<html>` as `data-theme="light"` or `data-theme="dark"`. On a first
  visit it follows the OS setting; once someone uses the theme toggle, their choice is saved
  in localStorage and wins from then on. A tiny inline script in `<head>` applies it before
  the page paints.
- Charts read their colors from the CSS variables at render time and are redrawn when the
  theme changes.
- The theme toggle is a quiet ghost button (var(--border), var(--text-muted)), never the accent.
