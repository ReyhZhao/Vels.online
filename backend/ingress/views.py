import ipaddress
import re

from django.conf import settings as django_settings
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from .bunkerweb import BunkerWebClient, BunkerWebError
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


class RouteListView(APIView):
    def get(self, request):
        slug = request.query_params.get("org", "")
        org, err = _resolve_org(request, slug)
        if err:
            return err
        routes = Route.objects.filter(organization=org).order_by("-created_at")
        return Response(RouteSerializer(routes, many=True).data)

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
            return Response(
                {"detail": f"BunkerWeb rejected the request: {exc}"},
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
    def get(self, request, fqdn):
        route, err = _get_route(request, fqdn)
        if err:
            return err
        return Response(RouteSerializer(route).data)

    def delete(self, request, fqdn):
        route, err = _get_route(request, fqdn)
        if err:
            return err

        try:
            BunkerWebClient().delete_service(fqdn)
        except BunkerWebError as exc:
            return Response(
                {"detail": f"BunkerWeb rejected the deletion: {exc}"},
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
}

_RATE_RE = re.compile(r"^\d+r/[smh]$")
_COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")


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

    return dict(data), None


class RouteSettingsView(APIView):
    def get(self, request, fqdn):
        _, err = _get_route(request, fqdn)
        if err:
            return err
        try:
            all_settings = BunkerWebClient().get_service_settings(fqdn)
        except BunkerWebError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        filtered = {k: v for k, v in all_settings.items() if k in _MANAGED_SETTINGS}
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


class RouteReportsView(APIView):
    def get(self, request, fqdn):
        _, err = _get_route(request, fqdn)
        if err:
            return err
        try:
            data = BunkerWebClient().get_service_reports(fqdn)
            entries = data if isinstance(data, list) else data.get("entries", [])
            return Response({"entries": entries})
        except BunkerWebError:
            return Response(
                {
                    "entries": [],
                    "message": "BunkerWeb is currently unavailable. No report data could be retrieved.",
                }
            )


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
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
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
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
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
            route = Route.objects.create(
                fqdn=fqdn,
                backend_host=svc.get("backend_host", ""),
                backend_port=svc.get("backend_port", 80),
                backend_protocol=svc.get("backend_protocol", Route.PROTOCOL_HTTP),
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
