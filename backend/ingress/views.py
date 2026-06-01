import ipaddress
import logging
import re

from django.conf import settings as django_settings

logger = logging.getLogger(__name__)
from django.db import IntegrityError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from security.opensearch import OpenSearchClient, OpenSearchError

from .bunkerweb import BunkerWebClient, BunkerWebError
from .filters import RouteFilterSet
from .models import Route
from .serializers import RouteSerializer
from .tasks import check_route_dns, push_route_settings


def _get_route(request, fqdn):
    """Returns (route, error_response). Enforces org membership; staff bypass."""
    try:
        route = Route.objects.select_related("organization").get(fqdn=fqdn)
    except Route.DoesNotExist:
        return None, Response(status=404)
    if not request.user.is_staff:
        if not OrganizationMembership.objects.filter(
            user=request.user, organization=route.organization
        ).exists():
            return None, Response(status=403)
    return route, None


def _resolve_org(request, slug):
    if not slug:
        return None, Response({"detail": "org is required."}, status=400)
    try:
        org = Organization.objects.get(slug=slug)
    except Organization.DoesNotExist:
        return None, Response(status=404)
    if not request.user.is_staff:
        if not OrganizationMembership.objects.filter(user=request.user, organization=org).exists():
            return None, Response(status=403)
    return org, None


class RouteListView(ListAPIView):
    filter_backends = [DjangoFilterBackend]
    filterset_class = RouteFilterSet
    serializer_class = RouteSerializer

    def get_queryset(self):
        slug = self.request.query_params.get("org", "")
        if not slug:
            raise ValidationError({"detail": "org is required."})
        try:
            org = Organization.objects.get(slug=slug)
        except Organization.DoesNotExist:
            raise NotFound()
        if not self.request.user.is_staff:
            if not OrganizationMembership.objects.filter(
                user=self.request.user, organization=org
            ).exists():
                raise PermissionDenied()
        return Route.objects.filter(organization=org).order_by("-created_at")

    def post(self, request):
        slug = request.query_params.get("org", "")
        org, err = _resolve_org(request, slug)
        if err:
            return err

        if org.max_routes is not None:
            if Route.objects.filter(organization=org).count() >= org.max_routes:
                return Response(
                    {
                        "detail": (
                            f"Route quota exceeded. "
                            f"This organisation is limited to {org.max_routes} route(s)."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        if Route.objects.filter(fqdn=request.data.get("fqdn", "")).exists():
            return Response(
                {"detail": "A route with this FQDN already exists."},
                status=status.HTTP_409_CONFLICT,
            )

        ser = RouteSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        fqdn = ser.validated_data["fqdn"]
        backend_host = ser.validated_data["backend_host"]
        backend_port = ser.validated_data["backend_port"]
        backend_protocol = ser.validated_data.get("backend_protocol", Route.PROTOCOL_HTTP)

        try:
            BunkerWebClient().create_service(fqdn, backend_host, backend_port, backend_protocol)
        except BunkerWebError as exc:
            logger.exception("BunkerWeb error creating service for fqdn=%s", fqdn)
            return Response(
                {"detail": "BunkerWeb rejected the request."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            route = ser.save(organization=org, status=Route.STATUS_ACTIVE)
        except IntegrityError:
            return Response(
                {"detail": "A route with this FQDN already exists."},
                status=status.HTTP_409_CONFLICT,
            )

        check_route_dns.delay(route.pk)
        return Response(RouteSerializer(route).data, status=status.HTTP_201_CREATED)


class RouteDetailView(APIView):
    _PATCH_FIELDS = {"name", "backend_host", "backend_port", "backend_protocol"}

    def get(self, request, fqdn):
        route, err = _get_route(request, fqdn)
        if err:
            return err
        return Response(RouteSerializer(route).data)

    def patch(self, request, fqdn):
        route, err = _get_route(request, fqdn)
        if err:
            return err

        data = {k: v for k, v in request.data.items() if k in self._PATCH_FIELDS}
        ser = RouteSerializer(route, data=data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        route = ser.save()
        push_route_settings.delay(
            fqdn,
            {
                "REVERSE_PROXY_HOST": f"{route.backend_host}:{route.backend_port}",
                "REVERSE_PROXY_SCHEME": route.backend_protocol,
            },
        )
        return Response(RouteSerializer(route).data)

    def delete(self, request, fqdn):
        route, err = _get_route(request, fqdn)
        if err:
            return err

        try:
            BunkerWebClient().delete_service(fqdn)
        except BunkerWebError as exc:
            logger.exception("BunkerWeb error deleting service for fqdn=%s", fqdn)
            return Response(
                {"detail": "BunkerWeb rejected the deletion."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        route.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Keys this app exposes; grows as more setting slices are added.
_MANAGED_SETTINGS = {
    # WAF
    "USE_MODSECURITY",
    "USE_MODSECURITY_CRS",
    "MODSECURITY_CRS_PARANOIA_LEVEL",
    "USE_REDIRECT_HTTP_TO_HTTPS",
    # IP whitelist
    "USE_WHITELIST",
    "WHITELIST_IP",
    # Rate limiting
    "USE_LIMIT_REQ",
    "LIMIT_REQ_RATE",
    "LIMIT_REQ_BURST",
    # Country access
    "BLACKLIST_COUNTRY",
    "WHITELIST_COUNTRY",
    # Bot protection
    "USE_ANTIBOT",
    "ANTIBOT_TYPE",
    "ANTIBOT_RECAPTCHA_SCORE",
    "ANTIBOT_RECAPTCHA_SITEKEY",
    "ANTIBOT_RECAPTCHA_SECRET",
    "ANTIBOT_HCAPTCHA_SITEKEY",
    "ANTIBOT_HCAPTCHA_SECRET",
    "ANTIBOT_TURNSTILE_SITEKEY",
    "ANTIBOT_TURNSTILE_SECRET",
    # Advanced — proxy
    "REVERSE_PROXY_CONNECT_TIMEOUT",
    "REVERSE_PROXY_READ_TIMEOUT",
    "REVERSE_PROXY_SEND_TIMEOUT",
    "USE_REVERSE_PROXY_WS",
    "USE_REVERSE_PROXY_BUFFERING",
    "REVERSE_PROXY_BUFFER_SIZE",
    "REVERSE_PROXY_BUFFERS",
    "REVERSE_PROXY_MAX_TEMP_FILE_SIZE",
    # Advanced — request
    "ALLOWED_METHODS",
    "MAX_CLIENT_SIZE",
    # Advanced — real IP
    "USE_REAL_IP",
    "REAL_IP_RECURSIVE",
    "REAL_IP_HEADER",
    # Advanced — CORS
    "USE_CORS",
    "CORS_ALLOW_ORIGIN",
    "CORS_ALLOW_HEADERS",
    "CORS_ALLOW_METHODS",
    "CORS_EXPOSE_HEADERS",
    "CORS_MAX_AGE",
    "CORS_ALLOW_CREDENTIALS",
}

_RATE_RE = re.compile(r"^\d+r/[smh]$")
_COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")
_MAX_CLIENT_SIZE_RE = re.compile(r"^\d+[kmgKMG]$")
_HTTP_VERBS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT", "TRACE"}
_ANTIBOT_TYPES = {"cookie", "javascript", "recaptcha", "hcaptcha", "turnstile"}
_PROXY_TIMEOUT_KEYS = (
    "REVERSE_PROXY_CONNECT_TIMEOUT",
    "REVERSE_PROXY_READ_TIMEOUT",
    "REVERSE_PROXY_SEND_TIMEOUT",
)


def _validate_settings(data):
    """Returns (cleaned_dict, error_str) where error_str is None on success."""
    unknown = set(data) - _MANAGED_SETTINGS
    if unknown:
        return None, f"Unknown settings key(s): {', '.join(sorted(unknown))}"

    if "MODSECURITY_CRS_PARANOIA_LEVEL" in data:
        try:
            level = int(data["MODSECURITY_CRS_PARANOIA_LEVEL"])
        except (TypeError, ValueError):
            return None, "MODSECURITY_CRS_PARANOIA_LEVEL must be an integer."
        if level < 1 or level > 4:
            return None, "MODSECURITY_CRS_PARANOIA_LEVEL must be between 1 and 4."

    if data.get("WHITELIST_IP"):
        for token in data["WHITELIST_IP"].split():
            try:
                ipaddress.ip_network(token, strict=False)
            except ValueError:
                return None, f"Invalid IP address or CIDR: {token!r}"

    if data.get("LIMIT_REQ_RATE"):
        if not _RATE_RE.match(data["LIMIT_REQ_RATE"]):
            return None, "LIMIT_REQ_RATE must be in format like '10r/s', '5r/m', or '2r/h'."

    if "LIMIT_REQ_BURST" in data and data["LIMIT_REQ_BURST"] not in ("", None):
        try:
            burst = int(data["LIMIT_REQ_BURST"])
        except (TypeError, ValueError):
            return None, "LIMIT_REQ_BURST must be an integer."
        if burst < 0:
            return None, "LIMIT_REQ_BURST must be a non-negative integer."

    for key in ("BLACKLIST_COUNTRY", "WHITELIST_COUNTRY"):
        if data.get(key):
            for token in data[key].split():
                if not _COUNTRY_CODE_RE.match(token):
                    return None, (
                        f"Invalid country code in {key}: {token!r}. "
                        "Must be 2-letter uppercase ISO 3166-1 alpha-2."
                    )

    if "USE_REDIRECT_HTTP_TO_HTTPS" in data and data["USE_REDIRECT_HTTP_TO_HTTPS"] not in ("", None):
        if data["USE_REDIRECT_HTTP_TO_HTTPS"] not in ("yes", "no"):
            return None, "USE_REDIRECT_HTTP_TO_HTTPS must be 'yes' or 'no'."

    for key in _PROXY_TIMEOUT_KEYS:
        if key in data and data[key] not in ("", None):
            try:
                val = int(data[key])
            except (TypeError, ValueError):
                return None, f"{key} must be a positive integer."
            if val <= 0:
                return None, f"{key} must be a positive integer."

    if "ALLOWED_METHODS" in data and data["ALLOWED_METHODS"] not in ("", None):
        for verb in str(data["ALLOWED_METHODS"]).split("|"):
            verb = verb.strip()
            if verb not in _HTTP_VERBS:
                return None, f"ALLOWED_METHODS contains unknown verb: {verb!r}."

    if "MAX_CLIENT_SIZE" in data and data["MAX_CLIENT_SIZE"] not in ("", None):
        val = str(data["MAX_CLIENT_SIZE"]).strip()
        if val != "0" and not _MAX_CLIENT_SIZE_RE.match(val):
            return None, (
                "MAX_CLIENT_SIZE must be a non-negative integer followed by k, m, or g, "
                "or 0 for unlimited."
            )

    if "ANTIBOT_TYPE" in data and data["ANTIBOT_TYPE"] not in ("", None):
        if data["ANTIBOT_TYPE"] not in _ANTIBOT_TYPES:
            return None, f"ANTIBOT_TYPE must be one of: {', '.join(sorted(_ANTIBOT_TYPES))}."

    if "ANTIBOT_RECAPTCHA_SCORE" in data and data["ANTIBOT_RECAPTCHA_SCORE"] not in ("", None):
        try:
            score = float(data["ANTIBOT_RECAPTCHA_SCORE"])
        except (TypeError, ValueError):
            return None, "ANTIBOT_RECAPTCHA_SCORE must be a float between 0.0 and 1.0."
        if score < 0.0 or score > 1.0:
            return None, "ANTIBOT_RECAPTCHA_SCORE must be between 0.0 and 1.0."

    if "CORS_MAX_AGE" in data and data["CORS_MAX_AGE"] not in ("", None):
        try:
            age = int(data["CORS_MAX_AGE"])
        except (TypeError, ValueError):
            return None, "CORS_MAX_AGE must be a non-negative integer."
        if age < 0:
            return None, "CORS_MAX_AGE must be a non-negative integer."

    return dict(data), None


class RouteSettingsView(APIView):
    def get(self, request, fqdn):
        _, err = _get_route(request, fqdn)
        if err:
            return err
        try:
            all_settings = BunkerWebClient().get_service_settings(fqdn)
        except BunkerWebError as exc:
            logger.exception("BunkerWeb error fetching settings for fqdn=%s", fqdn)
            return Response({"detail": "Service error contacting BunkerWeb."}, status=status.HTTP_502_BAD_GATEWAY)
        filtered = {k: v for k, v in all_settings.items() if k in _MANAGED_SETTINGS}
        if not filtered:
            logger.warning(
                "RouteSettingsView: no managed settings found for %s. "
                "BunkerWeb returned keys: %s",
                fqdn,
                list(all_settings.keys()),
            )
        return Response(filtered)

    def patch(self, request, fqdn):
        route, err = _get_route(request, fqdn)
        if err:
            return err

        cleaned, error = _validate_settings(request.data)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        push_route_settings.delay(fqdn, cleaned)
        return Response(cleaned)


class RouteLogsView(APIView):
    _VALID_TYPES = {"accesslog", "modsecurity"}

    def get(self, request, fqdn):
        _, err = _get_route(request, fqdn)
        if err:
            return err

        log_type = request.query_params.get("type", "accesslog")
        if log_type not in self._VALID_TYPES:
            return Response(
                {"detail": "type must be 'accesslog' or 'modsecurity'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            hours = int(request.query_params.get("hours", 24))
            offset = int(request.query_params.get("offset", 0))
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except ValueError:
            return Response(
                {"detail": "hours, offset, and limit must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        srcip = request.query_params.get("srcip") or None

        try:
            result = OpenSearchClient().get_route_logs(
                fqdn=fqdn,
                log_type=log_type,
                hours=hours,
                offset=offset,
                limit=limit,
                srcip=srcip,
            )
        except OpenSearchError:
            return Response({"logs": [], "total": 0, "summary": {"total": 0, "blocked": 0}})

        return Response(result)


class RouteImportView(APIView):
    def get(self, request):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        slug = request.query_params.get("org", "")
        _, err = _resolve_org(request, slug)
        if err:
            return err
        try:
            services = BunkerWebClient().list_services()
        except BunkerWebError as exc:
            logger.exception("BunkerWeb error listing services in RouteImportView.get")
            return Response({"detail": "Service error contacting BunkerWeb."}, status=status.HTTP_502_BAD_GATEWAY)
        existing = set(Route.objects.values_list("fqdn", flat=True))
        candidates = [s for s in services if s.get("server_name") not in existing]
        return Response({"candidates": candidates})

    def post(self, request):
        if not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)
        slug = request.query_params.get("org", "")
        org, err = _resolve_org(request, slug)
        if err:
            return err
        fqdns = request.data.get("fqdns", [])
        if not isinstance(fqdns, list) or not fqdns:
            return Response(
                {"detail": "fqdns must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            services = BunkerWebClient().list_services()
        except BunkerWebError as exc:
            logger.exception("BunkerWeb error listing services in RouteImportView.post")
            return Response({"detail": "Service error contacting BunkerWeb."}, status=status.HTTP_502_BAD_GATEWAY)
        bw_map = {s.get("server_name"): s for s in services}
        existing = set(Route.objects.values_list("fqdn", flat=True))
        for fqdn in fqdns:
            if fqdn not in bw_map:
                return Response(
                    {"detail": f"{fqdn!r} is not a known BunkerWeb service."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if fqdn in existing:
                return Response(
                    {"detail": f"{fqdn!r} is already imported."},
                    status=status.HTTP_409_CONFLICT,
                )
        if org.max_routes is not None:
            current = Route.objects.filter(organization=org).count()
            if current + len(fqdns) > org.max_routes:
                return Response(
                    {
                        "detail": (
                            f"Route quota exceeded. "
                            f"This organisation is limited to {org.max_routes} route(s)."
                        )
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
        created = []
        for fqdn in fqdns:
            svc = bw_map[fqdn]
            backend_host = svc.get("backend_host", "")
            backend_port = svc.get("backend_port", 80)
            backend_protocol = svc.get("backend_protocol", Route.PROTOCOL_HTTP)
            try:
                svc_settings = BunkerWebClient().get_service_settings(fqdn)
                rp_host = svc_settings.get("REVERSE_PROXY_HOST", "")
                if rp_host:
                    if ":" in rp_host:
                        host_part, port_part = rp_host.rsplit(":", 1)
                        try:
                            backend_port = int(port_part)
                        except ValueError:
                            host_part = rp_host
                        backend_host = host_part
                    else:
                        backend_host = rp_host
                rp_scheme = svc_settings.get("REVERSE_PROXY_SCHEME", "")
                if rp_scheme in (Route.PROTOCOL_HTTP, Route.PROTOCOL_HTTPS):
                    backend_protocol = rp_scheme
            except BunkerWebError:
                pass
            route = Route.objects.create(
                fqdn=fqdn,
                backend_host=backend_host,
                backend_port=backend_port,
                backend_protocol=backend_protocol,
                backend_type=Route.TYPE_DIRECT,
                organization=org,
                status=Route.STATUS_ACTIVE,
            )
            check_route_dns.delay(route.pk)
            created.append(route)
        return Response(RouteSerializer(created, many=True).data, status=status.HTTP_201_CREATED)


class IngressSettingsView(APIView):
    def get(self, request):
        return Response(
            {
                "bunkerweb_public_ip": getattr(django_settings, "BUNKERWEB_PUBLIC_IP", ""),
                "bunkerweb_public_fqdn": getattr(django_settings, "BUNKERWEB_PUBLIC_FQDN", ""),
            }
        )
