from rest_framework import serializers

from .models import Route

_SCHEMES = ("https://", "http://")


class RouteSerializer(serializers.ModelSerializer):
    org_slug = serializers.CharField(source="organization.slug", read_only=True)
    backend_asset_suggestion = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = [
            "id",
            "name",
            "fqdn",
            "backend_host",
            "backend_port",
            "backend_protocol",
            "backend_type",
            "backend_asset",
            "backend_asset_suggestion",
            "status",
            "dns_ok",
            "org_slug",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "dns_ok", "org_slug", "backend_asset_suggestion", "created_at", "updated_at"]

    def validate_backend_host(self, value):
        for scheme in _SCHEMES:
            if value.startswith(scheme):
                value = value[len(scheme):]
                break
        return value

    def get_backend_asset_suggestion(self, obj):
        from incidents.models import Asset
        from ingress.services.backend_match import match_backend_to_asset

        if obj.backend_asset_id is not None:
            return None
        candidates = list(Asset.objects.filter(organization=obj.organization, kind="host"))
        _, suggestions = match_backend_to_asset(obj, candidates)
        if not suggestions:
            return None
        first = suggestions[0]
        return {"id": first.pk, "name": first.name, "agent_name": first.agent_name}
