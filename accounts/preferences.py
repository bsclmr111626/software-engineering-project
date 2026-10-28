"""Reading user preferences and applying them to a request.

``preferences_for`` is the single entry point: it creates the row on first
use and caches it on the user object, so a request costs one query however
many templates and views ask for it.
"""

from .models import UserPreference

SESSION_EPOCH_KEY = "cg_session_epoch"
SESSION_STARTED_KEY = "cg_session_started"
SESSION_AGENT_KEY = "cg_session_agent"

START_PAGE_URLS = {
    "overview": "core:dashboard",
    "supply_chain": "core:supply_chain",
    "simulations": "simulation:hub",
    "reports": "reports:list",
}


def preferences_for(user):
    if user is None or not user.is_authenticated:
        return None
    cached = getattr(user, "_cg_preferences", None)
    if cached is None:
        cached, _ = UserPreference.objects.get_or_create(user=user)
        user._cg_preferences = cached
    return cached


def html_attributes(preferences):
    """The data-* attributes rendered on <html>. The CSS token blocks key off
    them, so components never need to know which preference is active."""
    if preferences is None:
        return {}
    attrs = {
        "data-theme-pref": preferences.color_mode,
        "data-accent": preferences.accent,
        "data-surface": preferences.surface,
        "data-text-size": preferences.text_size,
        "data-heading-font": preferences.heading_font,
        "data-density": preferences.density,
    }
    if preferences.reduce_motion:
        attrs["data-motion"] = "reduce"
    if preferences.increase_contrast:
        attrs["data-contrast"] = "more"
    if preferences.underline_links:
        attrs["data-links"] = "underline"
    return attrs


def page_size(request, default=25):
    preferences = preferences_for(getattr(request, "user", None))
    return preferences.page_size if preferences else default


def describe_agent(user_agent):
    """A short, human description of a User-Agent ("Chrome on Windows").

    Only this summary is kept in the session, never the raw header."""
    ua = user_agent or ""
    browser = next(
        (
            name
            for token, name in (
                ("Edg/", "Edge"),
                ("OPR/", "Opera"),
                ("Firefox/", "Firefox"),
                ("Chrome/", "Chrome"),
                ("Safari/", "Safari"),
            )
            if token in ua
        ),
        "Unknown browser",
    )
    system = next(
        (
            name
            for token, name in (
                ("Windows", "Windows"),
                ("Android", "Android"),
                ("iPhone", "iOS"),
                ("iPad", "iPadOS"),
                ("Mac OS X", "macOS"),
                ("Linux", "Linux"),
            )
            if token in ua
        ),
        "an unknown system",
    )
    return f"{browser} on {system}"
