from rest_framework import serializers

from .models import Route


class RouteSerializer(serializers.ModelSerializer):
    org_slug = serializers.CharField(source="organization.slug", read_only=True)

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
            "status",
            "dns_ok",
            "org_slug",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "status", "dns_ok", "org_slug", "created_at", "updated_at"]
