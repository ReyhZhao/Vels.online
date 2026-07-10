from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core.exceptions import MiddlewareNotUsed


class DevAutoLoginMiddleware:
    """
    Local-dev only: log every request in as the admin superuser so the SPA and
    Django admin require no interactive login.

    SAFETY: this is gated solely on settings.DEV_AUTO_LOGIN, which is fed by the
    DEV_AUTO_LOGIN env var set *only* in docker-compose.yaml. It deliberately does
    NOT key off DEBUG. When the flag is off, MiddlewareNotUsed drops the class from
    the middleware stack entirely, so there is no live code path in any environment
    that doesn't opt in.

    Works for DRF too: login() sets request.user on the underlying request, which
    SessionAuthentication reads back, so IsAuthenticated endpoints see the admin.
    """

    def __init__(self, get_response):
        if not settings.DEV_AUTO_LOGIN:
            raise MiddlewareNotUsed
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            user = (
                get_user_model()
                .objects.filter(is_superuser=True)
                .order_by("pk")
                .first()
            )
            if user is not None:
                user.backend = "django.contrib.auth.backends.ModelBackend"
                login(request, user)
                request.user = user
        return self.get_response(request)


class ForceHttpsMiddleware:
    """
    Ensure Django treats every request as HTTPS.

    BunkerWeb terminates TLS but may not always forward X-Forwarded-Proto,
    which causes allauth's request.build_absolute_uri() to produce http://
    callback URLs that Authentik rejects. This middleware sets the header
    unconditionally so SecurityMiddleware's SECURE_PROXY_SSL_HEADER check
    always succeeds (and HSTS is emitted) regardless of DEBUG. Local plain-HTTP
    dev is unaffected: allauth already builds https:// URLs via
    ACCOUNT_DEFAULT_HTTP_PROTOCOL, and dev does not rely on the forwarded header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.META["HTTP_X_FORWARDED_PROTO"] = "https"
        return self.get_response(request)
