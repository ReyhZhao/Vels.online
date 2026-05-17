from rest_framework import serializers

from .models import EmailTemplate, Notification, NotificationPreferences


class NotificationPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreferences
        fields = [
            "email_assignment", "inapp_assignment",
            "email_delegation", "inapp_delegation",
            "email_comment", "inapp_comment",
            "email_state_change", "inapp_state_change",
            "email_incident_alert", "inapp_incident_alert",
            "push_assignment", "push_delegation", "push_comment",
            "push_state_change", "push_incident_alert",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate(self, data):
        instance = self.instance

        def effective(field):
            if field in data:
                return data[field]
            return getattr(instance, field) if instance else True

        if not (effective("email_assignment") or effective("inapp_assignment")):
            raise serializers.ValidationError(
                "At least one channel must be enabled for assignment notifications."
            )
        if not (effective("email_delegation") or effective("inapp_delegation")):
            raise serializers.ValidationError(
                "At least one channel must be enabled for delegation notifications."
            )
        return data


class EmailTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailTemplate
        fields = ["name", "subject", "html_body", "description", "updated_at"]
        read_only_fields = ["name", "description", "updated_at"]


class NotificationSerializer(serializers.ModelSerializer):
    incident_id = serializers.IntegerField(source="incident.id", read_only=True, allow_null=True)
    incident_display_id = serializers.CharField(
        source="incident.display_id", read_only=True, allow_null=True
    )

    class Meta:
        model = Notification
        fields = ["id", "kind", "incident_id", "incident_display_id", "task_id", "payload", "created_at", "read_at"]
        read_only_fields = fields
