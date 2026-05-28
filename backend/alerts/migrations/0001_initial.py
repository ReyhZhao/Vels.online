from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("incidents", "0020_ioc_enrichment_data"),
        ("security", "0011_organization_alert_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Alert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_id", models.CharField(blank=True, max_length=20, unique=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="alerts",
                        to="security.organization",
                    ),
                ),
                (
                    "source_kind",
                    models.CharField(
                        choices=[
                            ("wazuh_event", "Wazuh Event"),
                            ("vulnerability", "Vulnerability"),
                            ("agent_finding", "Agent Finding"),
                            ("api", "API"),
                        ],
                        max_length=20,
                    ),
                ),
                ("source_ref", models.JSONField(blank=True, default=dict)),
                ("title", models.CharField(blank=True, max_length=500)),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("critical", "Critical"),
                            ("high", "High"),
                            ("medium", "Medium"),
                            ("low", "Low"),
                            ("info", "Info"),
                        ],
                        default="medium",
                        max_length=10,
                    ),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("new", "New"),
                            ("acknowledged", "Acknowledged"),
                            ("imported", "Imported"),
                            ("ignored", "Ignored"),
                        ],
                        default="new",
                        max_length=20,
                    ),
                ),
                (
                    "incident",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="alerts",
                        to="incidents.incident",
                    ),
                ),
                (
                    "acknowledged_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="acknowledged_alerts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
