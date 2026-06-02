import zoneinfo

from rest_framework import serializers

from .models import ShiftBlock, StaffProfile


class StaffProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffProfile
        fields = ["timezone"]

    def validate_timezone(self, value):
        if value not in zoneinfo.available_timezones():
            raise serializers.ValidationError(f"'{value}' is not a valid IANA timezone.")
        return value


class ShiftBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShiftBlock
        fields = ["id", "label", "start_time", "end_time", "order"]
