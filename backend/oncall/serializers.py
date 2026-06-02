import zoneinfo

from rest_framework import serializers

from .models import RotationTemplateSlot, ShiftBlock, ShiftOverride, StaffProfile


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


class ShiftOverrideSerializer(serializers.ModelSerializer):
    original_analyst_name = serializers.SerializerMethodField()
    override_analyst_name = serializers.SerializerMethodField()
    initiated_by_name = serializers.SerializerMethodField()
    shift_block_label = serializers.SerializerMethodField()

    class Meta:
        model = ShiftOverride
        fields = [
            "id", "date", "shift_block", "shift_block_label",
            "original_analyst", "original_analyst_name",
            "override_analyst", "override_analyst_name",
            "initiated_by", "initiated_by_name",
            "status", "kind", "note", "created_at", "resolved_at",
        ]
        read_only_fields = ["id", "status", "created_at", "resolved_at", "initiated_by"]

    def get_original_analyst_name(self, obj):
        return obj.original_analyst.get_full_name() or obj.original_analyst.username

    def get_override_analyst_name(self, obj):
        return obj.override_analyst.get_full_name() or obj.override_analyst.username

    def get_initiated_by_name(self, obj):
        return obj.initiated_by.get_full_name() or obj.initiated_by.username

    def get_shift_block_label(self, obj):
        return obj.shift_block.label


class ShiftOverrideCreateSerializer(serializers.Serializer):
    date = serializers.DateField()
    shift_block_id = serializers.IntegerField()
    override_analyst_id = serializers.IntegerField()
    original_analyst_id = serializers.IntegerField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=["swap", "cover_offer"], default="swap")

    def validate_shift_block_id(self, value):
        if not ShiftBlock.objects.filter(pk=value).exists():
            raise serializers.ValidationError("ShiftBlock not found.")
        return value

    def validate_override_analyst_id(self, value):
        from django.contrib.auth.models import User
        if not User.objects.filter(pk=value, is_staff=True).exists():
            raise serializers.ValidationError("Override analyst not found or not staff.")
        return value

    def validate_original_analyst_id(self, value):
        if value is not None:
            from django.contrib.auth.models import User
            if not User.objects.filter(pk=value).exists():
                raise serializers.ValidationError("Original analyst not found.")
        return value
