from rest_framework import serializers

from .models import MonitorVisibility


class MonitorLogSerializer(serializers.Serializer):
    datetime = serializers.CharField()
    type = serializers.CharField()
    duration_seconds = serializers.IntegerField(allow_null=True)


class MonitorSerializer(serializers.Serializer):
    name = serializers.CharField()
    status = serializers.CharField()
    uptime_ratio = serializers.CharField(allow_null=True)
    response_time = serializers.CharField(allow_null=True)
    logs = MonitorLogSerializer(many=True, required=False)


class MonitorAdminSerializer(serializers.Serializer):
    monitor_id = serializers.CharField()
    name = serializers.CharField()
    is_visible = serializers.BooleanField()


class MonitorVisibilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = MonitorVisibility
        fields = ["monitor_id", "name", "is_visible"]


class MonitorVisibilityPatchSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, default="")
    is_visible = serializers.BooleanField()
