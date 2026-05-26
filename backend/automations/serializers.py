from rest_framework import serializers

from .models import Automation


class AutomationSerializer(serializers.ModelSerializer):
    created_by = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Automation
        fields = [
            "id",
            "name",
            "semaphore_template_id",
            "semaphore_template_name",
            "default_vars",
            "incident_var_mappings",
            "archived",
            "created_by",
            "created_at",
            "updated_at",
        ]
