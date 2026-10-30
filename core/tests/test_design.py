"""Pin the DESIGN.md rules that can be checked statically.

Colours are defined only between the @tokens markers of codeguard.css (the
light and dark themes, the accent themes and increased contrast); everything
else (components, templates, JavaScript) must use the tokens and never branch
on the theme.
"""

import re
from pathlib import Path

from django.conf import settings

from simulation import charts

BASE = Path(settings.BASE_DIR)
CSS = (BASE / "static" / "css" / "codeguard.css").read_text(encoding="utf-8")
# Hex, rgb()/hsl(), and white/black used as a value (not white-space).
COLOUR_LITERAL = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|[:\s](?:white|black)\s*[;)!,]")
TOKEN = re.compile(r"--([a-z-]+):\s*(#[0-9A-Fa-f]{6});")
START, END = "/* @tokens:start */", "/* @tokens:end */"
TOKENS = CSS[CSS.index(START) : CSS.index(END)]
COMPONENTS = CSS.replace(TOKENS, "")


def _block(selector):
    start = TOKENS.index(selector + " {")
    return TOKENS[start : TOKENS.index("}", start) + 1]


LIGHT = _block(':root, [data-theme="light"]')
DARK = _block('[data-theme="dark"]')


def _tokens(block):
    return {name: value.upper() for name, value in TOKEN.findall(block)}


def test_both_themes_define_the_same_tokens():
    assert len(_tokens(LIGHT)) >= 20
    assert _tokens(LIGHT).keys() == _tokens(DARK).keys()
    assert "--shadow-overlay" in LIGHT and "--shadow-overlay" in DARK


def test_variants_only_override_existing_tokens():
    names = set(_tokens(LIGHT)) | {"shadow-overlay"}
    for selector in ('[data-accent="iris"]', '[data-accent="graphite"]', '[data-contrast="more"]'):
        for dark in (False, True):
            block = _block(('[data-theme="dark"]' if dark else "") + selector)
            assert set(_tokens(block)) <= names, selector
    # Surfaces change only surfaces, hairlines and secondary ink, never ink, accent or risk colours.
    allowed = {"bg", "surface", "surface-sunken", "surface-raised", "border", "border-strong", "text-muted"}
    for surface in ("pearl", "sage"):
        tokens = _tokens(_block(f'[data-theme="light"][data-surface="{surface}"]'))
        assert set(tokens) == allowed, surface
    assert '[data-surface="neutral"]' not in TOKENS  # retired; see accounts migration 0006


def test_increased_contrast_wins_over_surface_variants():
    # Same specificity as the surface blocks and declared after them.
    for surface in ("pearl", "sage"):
        assert TOKENS.index('[data-theme="light"][data-contrast="more"]') > TOKENS.index(
            f'[data-theme="light"][data-surface="{surface}"]'
        )


def test_colours_are_defined_only_in_the_token_blocks():
    assert COLOUR_LITERAL.findall(COMPONENTS) == []


def test_components_never_branch_on_the_theme():
    assert "color-scheme: dark" in TOKENS
    assert "data-theme" not in COMPONENTS
    assert "data-bs-theme" not in COMPONENTS
    assert "prefers-color-scheme" not in COMPONENTS


def test_templates_and_scripts_use_no_colour_literals_inline_styles_or_dark_classes():
    files = [*(BASE / "templates").rglob("*.html"), *(BASE / "static" / "js").rglob("*.js")]
    banned = re.compile(
        r'data-bs-theme="|\sstyle="|btn-outline-light|tag-accent"|bg-dark|text-bg-|text-(?:info|warning|white)\b'
    )
    offenders = {
        str(p.relative_to(BASE)): hits
        for p in files
        if (hits := COLOUR_LITERAL.findall(text := p.read_text(encoding="utf-8")) + banned.findall(text))
    }
    assert offenders == {}


def test_no_colour_gradients_glows_or_uppercase_labels():
    # The only gradient is the dot-grid paper texture behind diagrams.
    assert re.findall(r"(?:linear|conic)-gradient\(", COMPONENTS) == []
    assert re.findall(r"radial-gradient\((?!var\(--border\) 1px, transparent 1px\))", COMPONENTS) == []
    assert "text-transform: uppercase" not in COMPONENTS
    # Shadows: the overlay token (menus, tooltips) or hairline/inset rings with no blur.
    for shadow in re.findall(r"box-shadow:\s*([^;]+);", COMPONENTS):
        assert shadow.strip() in ("none", "var(--shadow-overlay)") or re.fullmatch(
            r"(inset )?\d+(px)? \d+(px)? 0( \d+px)? var\(--[a-z-]+\)", shadow.strip()
        ), shadow


def test_default_chart_palette_is_the_light_theme():
    light = _tokens(LIGHT)
    assert charts.DEFAULT_PALETTE.query == ",".join(light[t].lstrip("#") for t in charts.PALETTE_TOKENS)


def test_chart_tokens_in_javascript_match_the_server_order():
    js = (BASE / "static" / "js" / "app.js").read_text(encoding="utf-8")
    listed = re.search(r"CHART_TOKENS = \[(.*?)\];", js, re.S).group(1)
    assert tuple(re.findall(r'"([a-z-]+)"', listed)) == charts.PALETTE_TOKENS


def test_every_preference_value_has_a_style_hook():
    from accounts.models import Accent, Density, HeadingFont, Surface, TextSize

    for value in Accent.values[1:]:
        assert f'[data-accent="{value}"]' in TOKENS
    for value in Surface.values[1:]:
        assert f'[data-surface="{value}"]' in TOKENS
    for value in ("small", "large", "larger"):
        assert f'html[data-text-size="{value}"]' in COMPONENTS and value in TextSize.values
    assert 'html[data-density="compact"]' in COMPONENTS and "compact" in Density.values
    assert 'html[data-heading-font="sans"]' in COMPONENTS and "sans" in HeadingFont.values
    assert 'html[data-motion="reduce"]' in COMPONENTS
    assert 'html[data-links="underline"]' in COMPONENTS
