CONTENT_SECURITY_POLICY = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                           "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


class SecurityHeaders:
    """Headers Django doesn't add by itself (it already sets X-Frame-Options and nosniff).

    The Content Security Policy only allows scripts and styles from our own files,
    so even if someone managed to inject HTML, a <script> in it wouldn't run.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if not request.path.startswith("/admin/"):        # Django's admin uses inline scripts
            response.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        if request.user.is_authenticated:
            response.setdefault("Cache-Control", "private, no-store")   # pages with personal details
        return response
