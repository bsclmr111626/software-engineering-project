import re

from django import template
from django.contrib.humanize.templatetags.humanize import naturaltime
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from core.theme import INIT_SCRIPT
from simulation.charts import DEFAULT_PALETTE
from simulation.engine import STATE_LABELS
from simulation.risk import classify

register = template.Library()

STATE_ICONS = {
    "entry": "bi-play-circle-fill",
    "compromised": "bi-x-octagon-fill",
    "blocked": "bi-shield-fill-check",
    "exposed": "bi-exclamation-triangle-fill",
    "unaffected": "bi-check-circle",
}

OUTCOME_META = {
    "propagated": ("Propagated", "bi-arrow-right-circle-fill", "state-compromised"),
    "blocked_by_controls": ("Blocked by controls", "bi-shield-fill-check", "state-blocked"),
    "below_threshold": ("Below threshold", "bi-dash-circle", "state-exposed"),
}

RISK_ICONS = {
    "low": "bi-check-circle-fill",
    "moderate": "bi-exclamation-circle-fill",
    "high": "bi-exclamation-triangle-fill",
    "critical": "bi-x-octagon-fill",
}


@register.filter
def state_label(state):
    return STATE_LABELS.get(state, state.replace("_", " ").title() if state else "")


@register.filter
def state_icon(state):
    return STATE_ICONS.get(state, "bi-circle")


@register.filter
def outcome_label(outcome):
    return OUTCOME_META.get(outcome, (outcome, "", ""))[0]


@register.filter
def outcome_icon(outcome):
    return OUTCOME_META.get(outcome, ("", "bi-circle", ""))[1]


@register.filter
def outcome_class(outcome):
    return OUTCOME_META.get(outcome, ("", "", "state-unaffected"))[2]


@register.filter
def risk_class(score):
    """Classification label for a numeric score, or pass a label through."""
    if score is None or score == "":
        return "none"
    if isinstance(score, str):
        return score
    return classify(score)


@register.filter
def risk_icon(label):
    return RISK_ICONS.get(label, "bi-circle")


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def level_dots(value):
    """Render a 1-5 level as filled/empty dots (text, not colour)."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return ""
    return "●" * value + "○" * (5 - value)


@register.simple_tag
def theme_init_script():
    """The inline pre-paint theme script (allowed by its hash in the CSP)."""
    return mark_safe(f"<script>{INIT_SCRIPT}</script>")  # noqa: S308 - a fixed constant, never user input


@register.simple_tag
def default_chart_palette():
    """The ?palette= value a chart URL renders with when none is given."""
    return DEFAULT_PALETTE.query


@register.filter
def initials(username):
    """Up to two initials for the avatar: "demo_admin" -> "DA", "alice" -> "A"."""
    parts = [part for part in re.split(r"[\W_]+", str(username)) if part]
    return "".join(part[0] for part in parts[:2]).upper() or "?"


@register.filter
def display_initials(user):
    """Initials from the full name when there is one, else from the username."""
    full = f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip()
    return initials(full) if full else initials(user.get_username())


@register.simple_tag(takes_context=True)
def when(context, value):
    """A timestamp in the user's chosen style (Settings > Display), always
    with the exact time in the datetime attribute and the tooltip."""
    if not value:
        return "—"
    local = timezone.localtime(value) if timezone.is_aware(value) else value
    exact = date_format(local, "Y-m-d H:i")
    preferences = context.get("prefs")
    shown = exact if preferences is not None and preferences.timestamp_style == "absolute" else naturaltime(value)
    return format_html('<time datetime="{}" title="{}">{}</time>', value.isoformat(), exact, shown)


@register.simple_tag(takes_context=True)
def query_with(context, **changes):
    """The current query string with some parameters replaced (page reset)."""
    params = context["request"].GET.copy()
    params.pop("page", None)
    for key, value in changes.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"


@register.filter
def level_ticks(value):
    """A 1-5 level as five ticks; the number is always printed beside it."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = 0
    ticks = "".join('<i class="on"></i>' if i < value else "<i></i>" for i in range(5))
    return mark_safe(f'<span class="cg-level" aria-hidden="true">{ticks}</span>')  # noqa: S308 - fixed markup
