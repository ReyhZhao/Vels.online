import zoneinfo

from rest_framework import serializers

from .models import RotationTemplateSlot, ShiftBlock, StaffProfile


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


class RotationTemplateSlotSerializer(serializers.ModelSerializer):
    analyst_name = serializers.SerializerMethodField()

    class Meta:
        model = RotationTemplateSlot
        fields = ["id", "day_of_week", "shift_block", "analyst_id", "analyst_name"]

    def get_analyst_name(self, obj):
        if obj.analyst:
            return obj.analyst.get_full_name() or obj.analyst.username
        return None


class RotationTemplateSlotWriteSerializer(serializers.Serializer):
    day_of_week = serializers.IntegerField(min_value=0, max_value=6)
    shift_block_id = serializers.IntegerField()
    analyst_id = serializers.IntegerField(allow_null=True, required=False)

    def validate_shift_block_id(self, value):
        if not ShiftBlock.objects.filter(pk=value).exists():
            raise serializers.ValidationError("ShiftBlock not found.")
        return value

    def validate_analyst_id(self, value):
        if value is not None:
            from django.contrib.auth.models import User
            if not User.objects.filter(pk=value).exists():
                raise serializers.ValidationError("User not found.")
        return value
