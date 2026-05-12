from django.conf import settings as django_settings
from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import Organization, OrganizationMembership

from .bunkerweb import BunkerWebClient, BunkerWebError
from .models import Route
from .serializers import RouteSerializer
from .tasks import check_route_dns


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


class IngressSettingsView(APIView):
    def get(self, request):
        return Response(
            {"bunkerweb_public_ip": getattr(django_settings, "BUNKERWEB_PUBLIC_IP", "")}
        )
