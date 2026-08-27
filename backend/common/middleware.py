class APISecurityHeadersMiddleware:
    """Defense-in-depth headers for API and bundled Swagger responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/api/"):
            return response
        if request.path.startswith("/api/docs/"):
            policy = (
                "default-src 'none'; script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                "font-src 'self'; connect-src 'self'; object-src 'none'; "
                "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
            )
        else:
            policy = "default-src 'none'; base-uri 'none'; frame-ancestors 'none'"
        response.setdefault("Content-Security-Policy", policy)
        response.setdefault(
            "Permissions-Policy", "camera=(), geolocation=(), microphone=(), payment=()"
        )
        return response
