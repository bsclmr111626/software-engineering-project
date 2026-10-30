from core.theme import INIT_SCRIPT_HASH


class ContentSecurityPolicyMiddleware:
    """Send a strict Content-Security-Policy header.

    CSS, JavaScript and images are served from this origin (Bootstrap is
    vendored under static/vendor). The only third-party origins are Google
    Fonts, for the Source Serif 4 heading face required by DESIGN.md. The
    only inline script allowed is the pre-paint theme script, by its hash
    (core/theme.py); no other inline scripts or styles run.
    """

    POLICY = "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' {INIT_SCRIPT_HASH}",
            "style-src 'self' https://fonts.googleapis.com",
            "img-src 'self' data:",
            "font-src 'self' https://fonts.gstatic.com",
            "connect-src 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "object-src 'none'",
        ]
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):
            response.setdefault("Content-Security-Policy", self.POLICY)
        response.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
