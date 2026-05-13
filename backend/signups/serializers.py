from rest_framework import serializers

from .models import SignupRequest


class SignupSubmitSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=255)
    org_name = serializers.CharField(max_length=255)
    intended_use = serializers.CharField()
    cf_turnstile_response = serializers.CharField()
    website = serializers.CharField(required=False, default="", allow_blank=True)  # honeypot


class SignupRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = SignupRequest
        fields = [
            "id",
            "email",
            "full_name",
            "org_name",
            "intended_use",
            "status",
            "approved_org_name",
            "org_slug",
            "invite_token",
            "invite_expires_at",
            "rejection_reason",
            "rejection_note",
            "send_rejection_email",
            "submitted_at",
            "actioned_at",
        ]
        read_only_fields = fields


class ApproveSerializer(serializers.Serializer):
    approved_org_name = serializers.CharField(max_length=255, required=False, allow_blank=True)


REJECTION_REASONS = [
    "Unable to verify organisation",
    "Duplicate request",
    "Outside our service area",
    "Incomplete information",
    "Other",
]


class RejectSerializer(serializers.Serializer):
    rejection_reason = serializers.ChoiceField(choices=REJECTION_REASONS)
    rejection_note = serializers.CharField(required=False, default="", allow_blank=True)
    send_rejection_email = serializers.BooleanField(default=True)
