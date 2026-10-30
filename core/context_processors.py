"""Context shared by every page of the application shell."""

import logging

from django.db import DatabaseError

from accounts.preferences import html_attributes, preferences_for

from .notifications import unread_count

# (namespace, url_name) -> primary navigation section. A namespace alone
# (url_name None) covers every page in it. Views may pass "nav_section"
# themselves to override this.
NAV_SECTIONS = {
    ("core", "dashboard"): "overview",
    ("core", "supply_chain"): "supply_chain",
    ("core", "stage_detail"): "supply_chain",
    ("core", "risk"): "risk",
    ("core", "notifications"): "notifications",
    ("core", "help"): "help",
    ("threats", "controls"): "controls",
    ("threats", "control_detail"): "controls",
    ("threats", None): "threats",
    ("simulation", "hub"): "simulations",
    ("simulation", "configure"): "simulations",
    ("simulation", "results"): "results",
    ("simulation", "detail"): "results",
    ("simulation", "compare"): "risk",
    ("reports", None): "reports",
    ("remediation", None): "remediation",
    ("audit", None): "activity",
    ("settings", None): "settings",
}


def nav_section(request):
    match = getattr(request, "resolver_match", None)
    if match is None:
        return ""
    return NAV_SECTIONS.get((match.namespace, match.url_name)) or NAV_SECTIONS.get((match.namespace, None), "")


def shell(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"html_attrs": {}}
    try:
        preferences = preferences_for(user)
        unread = unread_count(user)
    except DatabaseError:  # e.g. while rendering the 500 page during an outage
        logging.getLogger("codeguard").exception("Shell context unavailable")
        return {"html_attrs": {}}
    return {
        "prefs": preferences,
        "html_attrs": html_attributes(preferences),
        "nav_section": nav_section(request),
        "unread_notifications": unread,
    }
