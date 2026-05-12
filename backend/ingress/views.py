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
    def _get_route(self, request, fqdn):
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

    def get(self, request, fqdn):
        route, err = self._get_route(request, fqdn)
        if err:
            return err
        return Response(RouteSerializer(route).data)

    def delete(self, request, fqdn):
        route, err = self._get_route(request, fqdn)
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
    "USE_MODSECURITY",
    "USE_MODSECURITY_CRS",
    "MODSECURITY_CRS_PARANOIA_LEVEL",
}

_BOOLEAN_SETTINGS = {"USE_MODSECURITY", "USE_MODSECURITY_CRS"}


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

    return dict(data), None


class RouteSettingsView(APIView):
    def _get_route(self, request, fqdn):
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

    def get(self, request, fqdn):
        _, err = self._get_route(request, fqdn)
        if err:
            return err
        try:
            all_settings = BunkerWebClient().get_service_settings(fqdn)
        except BunkerWebError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        filtered = {k: v for k, v in all_settings.items() if k in _MANAGED_SETTINGS}
        return Response(filtered)

    def patch(self, request, fqdn):
        route, err = self._get_route(request, fqdn)
        if err:
            return err

        cleaned, error = _validate_settings(request.data)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)

        push_route_settings.delay(fqdn, cleaned)
        return Response(cleaned)


class IngressSettingsView(APIView):
    def get(self, request):
        return Response(
            {"bunkerweb_public_ip": getattr(django_settings, "BUNKERWEB_PUBLIC_IP", "")}
        )
