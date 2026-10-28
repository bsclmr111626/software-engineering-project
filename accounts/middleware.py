from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from .preferences import SESSION_EPOCH_KEY, preferences_for


class SessionEpochMiddleware:
    """Ends sessions that were revoked with "Sign out of other sessions".

    Each session stores the user's session epoch at sign-in. Revoking
    increments the epoch, so every older session no longer matches and is
    signed out on its next request. Sessions created before this feature
    existed adopt the current epoch the first time they are seen.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            epoch = preferences_for(user).session_epoch
            stored = request.session.get(SESSION_EPOCH_KEY)
            if stored is None:
                request.session[SESSION_EPOCH_KEY] = epoch
            elif stored != epoch:
                logout(request)
                messages.info(request, "This session was signed out from another device. Sign in again to continue.")
                return redirect("accounts:login")
        return self.get_response(request)
