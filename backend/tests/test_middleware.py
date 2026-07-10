import pytest
from django.test import RequestFactory, override_settings

from config.middleware import ForceHttpsMiddleware


def make_middleware(get_response=None):
    if get_response is None:
        get_response = lambda request: None  # noqa: E731
    return ForceHttpsMiddleware(get_response)


@pytest.fixture
def factory():
    return RequestFactory()


@override_settings(DEBUG=False)
def test_sets_forwarded_proto_https_in_production(factory):
    request = factory.get("/")
    assert request.META.get("HTTP_X_FORWARDED_PROTO") != "https"

    make_middleware()(request)

    assert request.META["HTTP_X_FORWARDED_PROTO"] == "https"


@override_settings(DEBUG=True)
def test_sets_forwarded_proto_unconditionally_even_in_debug(factory):
    # Decoupled from DEBUG (#684): the header is set regardless so HSTS/Secure
    # cookies and allauth https:// callbacks work once prod runs DEBUG=False.
    request = factory.get("/")
    request.META.pop("HTTP_X_FORWARDED_PROTO", None)

    make_middleware()(request)

    assert request.META["HTTP_X_FORWARDED_PROTO"] == "https"


@override_settings(DEBUG=False)
def test_calls_get_response(factory):
    called = []

    def get_response(req):
        called.append(req)
        return "response"

    request = factory.get("/")
    result = make_middleware(get_response)(request)

    assert called == [request]
    assert result == "response"


@override_settings(DEBUG=False)
def test_request_is_secure_after_middleware(factory):
    """SecurityMiddleware's SECURE_PROXY_SSL_HEADER check should now succeed."""
    from django.test import override_settings as _ov

    request = factory.get("/")
    make_middleware()(request)

    # request.is_secure() reads HTTP_X_FORWARDED_PROTO via SECURE_PROXY_SSL_HEADER
    assert request.META["HTTP_X_FORWARDED_PROTO"] == "https"
