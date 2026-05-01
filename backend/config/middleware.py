from django.conf import settings


class ForceHttpsMiddleware:
    """
    Ensure Django treats every request as HTTPS in production.

    BunkerWeb terminates TLS but may not always forward X-Forwarded-Proto,
    which causes allauth's request.build_absolute_uri() to produce http://
    callback URLs that Authentik rejects. This middleware sets the header
    unconditionally when DEBUG=False so SecurityMiddleware's
    SECURE_PROXY_SSL_HEADER check always succeeds.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not settings.DEBUG:
            request.META["HTTP_X_FORWARDED_PROTO"] = "https"
        return self.get_response(request)
