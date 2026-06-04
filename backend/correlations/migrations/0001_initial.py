import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("incidents", "0026_add_correlation_source_kind"),
        ("security", "0011_organization_alert_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="CorrelationRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "correlation_key",
                    models.CharField(
                        choices=[
                            ("host.name", "Host (host.name)"),
                            ("source.ip", "Source IP (source.ip)"),
                            ("user.name", "Username (user.name)"),
                            ("file.hash.sha256", "File Hash (file.hash.sha256)"),
                            ("process.name", "Process (process.name)"),
                            ("none", "None (org-wide)"),
                        ],
                        default="none",
                        max_length=50,
                    ),
                ),
                ("window_minutes", models.PositiveIntegerField(default=60)),
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
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="correlation_rules",
                        to="security.organization",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="CorrelationRuleLeg",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("count", models.PositiveIntegerField(default=1)),
                ("display_order", models.PositiveIntegerField(default=0)),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="legs",
                        to="correlations.correlationrule",
                    ),
                ),
            ],
            options={"ordering": ["display_order", "id"]},
        ),
        migrations.CreateModel(
            name="LegCondition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "field_kind",
                    models.CharField(
                        choices=[
                            ("alert_field", "Alert field"),
                            ("entity", "ECS entity"),
                            ("source_ref", "Source ref key"),
                        ],
                        max_length=20,
                    ),
                ),
                ("field_name", models.CharField(max_length=100)),
                (
                    "operator",
                    models.CharField(
                        choices=[
                            ("equals", "Equals"),
                            ("in", "In"),
                            ("contains", "Contains"),
                            ("gte", "Severity >="),
                            ("lte", "Severity <="),
                            ("cidr", "IP in CIDR"),
                        ],
                        max_length=10,
                    ),
                ),
                ("value", models.TextField()),
                (
                    "leg",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="conditions",
                        to="correlations.correlationruleleg",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="CorrelationFiring",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("entity_value", models.CharField(default="none", max_length=500)),
                ("fired_at", models.DateTimeField(auto_now_add=True)),
                (
                    "incident",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="correlation_firings",
                        to="incidents.incident",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="correlation_firings",
                        to="security.organization",
                    ),
                ),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="firings",
                        to="correlations.correlationrule",
                    ),
                ),
            ],
            options={"ordering": ["-fired_at"]},
        ),
        migrations.CreateModel(
            name="SystemRuleMute",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="system_rule_mutes",
                        to="security.organization",
                    ),
                ),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mutes",
                        to="correlations.correlationrule",
                    ),
                ),
            ],
            options={"unique_together": {("organization", "rule")}},
        ),
    ]
