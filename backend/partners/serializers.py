import logging
import re

from rest_framework import serializers

from .models import Connection, ConnectionSender, IntakeInboxMessage

logger = logging.getLogger(__name__)


class ConnectionSerializer(serializers.ModelSerializer):
    # Written as a flat list of addresses; the child ConnectionSender rows are managed
    # here. Read back via to_representation so the API round-trips a plain list.
    sender_addresses = serializers.ListField(
        child=serializers.EmailField(), write_only=True, allow_empty=False
    )
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = Connection
        fields = [
            "id",
            "name",
            "kind",
            "organization",
            "organization_name",
            "direction",
            "external_reference_regex",
            "field_mappings",
            "sender_addresses",
            "active",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["sender_addresses"] = [s.address for s in instance.senders.all()]
        return data

    def validate_sender_addresses(self, value):
        normalized, seen = [], set()
        for addr in value:
            a = (addr or "").strip().lower()
            if not a:
                continue
            if a in seen:
                raise serializers.ValidationError(f"Duplicate address in this Connection: {a}")
            seen.add(a)
            normalized.append(a)
        if not normalized:
            raise serializers.ValidationError("At least one sender address is required.")
        # Sender addresses are unique across ALL Connections (ADR-0032).
        conflict_qs = ConnectionSender.objects.filter(address__in=normalized)
        if self.instance is not None:
            conflict_qs = conflict_qs.exclude(connection=self.instance)
        conflicts = sorted(conflict_qs.values_list("address", flat=True))
        if conflicts:
            raise serializers.ValidationError(
                f"Already used by another Connection: {', '.join(conflicts)}"
            )
        return normalized

    def validate_external_reference_regex(self, value):
        if value:
            try:
                re.compile(value)
            except re.error as exc:
                # Log the detailed compile error for operators; return a generic
                # message so exception internals aren't echoed back (CWE-209).
                logger.warning("Invalid external_reference_regex submitted: %s", exc)
                raise serializers.ValidationError("Invalid regular expression.")
        return value

    def validate_field_mappings(self, value):
        if not value:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Must be an object keyed by field name.")
        cleaned = {}
        for field, cfg in value.items():
            if field not in Connection.MAPPED_FIELDS:
                raise serializers.ValidationError(f"Unknown mapped field: {field}")
            if not isinstance(cfg, dict):
                raise serializers.ValidationError(f"{field}: mapping must be an object.")
            regex = cfg.get("regex") or ""
            if regex:
                try:
                    re.compile(regex)
                except re.error as exc:
                    # `field` is a validated MAPPED_FIELDS key (safe to echo); the
                    # exception detail is logged, not returned to the caller (CWE-209).
                    logger.warning("Invalid field mapping regex for %s: %s", field, exc)
                    raise serializers.ValidationError(
                        f"{field}: invalid regular expression."
                    )
            value_map = cfg.get("value_map") or {}
            if not isinstance(value_map, dict):
                raise serializers.ValidationError(f"{field}: value_map must be an object.")
            cleaned[field] = {
                "regex": regex,
                "value_map": value_map,
                "default": cfg.get("default") or "",
            }
        return cleaned

    def create(self, validated_data):
        addresses = validated_data.pop("sender_addresses")
        request = self.context.get("request")
        if request is not None and request.user.is_authenticated:
            validated_data["created_by"] = request.user
        connection = Connection.objects.create(**validated_data)
        ConnectionSender.objects.bulk_create(
            [ConnectionSender(connection=connection, address=a) for a in addresses]
        )
        return connection

    def update(self, instance, validated_data):
        addresses = validated_data.pop("sender_addresses", None)
        for key, val in validated_data.items():
            setattr(instance, key, val)
        instance.save()
        if addresses is not None:
            instance.senders.all().delete()
            ConnectionSender.objects.bulk_create(
                [ConnectionSender(connection=instance, address=a) for a in addresses]
            )
        return instance


class IntakeInboxMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntakeInboxMessage
        fields = ["id", "sender", "subject", "drop_reason", "body_excerpt", "received_at"]
        read_only_fields = fields
