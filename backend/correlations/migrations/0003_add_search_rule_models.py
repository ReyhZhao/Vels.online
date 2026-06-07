import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0005_add_scheduled_search_source_kind"),
        ("correlations", "0002_add_detection_suggestion"),
        ("incidents", "0027_add_scheduled_search_source_kind"),
        ("security", "0012_add_llm_residual_autocreate_threshold"),
    ]

    operations = [
        migrations.CreateModel(
            name="SearchRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("description", models.TextField(blank=True, default="")),
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
                ("window_minutes", models.PositiveIntegerField(default=60)),
                ("interval_minutes", models.PositiveIntegerField(default=60)),
                ("max_findings_per_run", models.PositiveIntegerField(default=50)),
                ("enabled", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="search_rules",
                        to="security.organization",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="SearchRuleLeg",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_order", models.PositiveIntegerField(default=0)),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="legs",
                        to="correlations.searchrule",
                    ),
                ),
            ],
            options={"ordering": ["display_order", "id"]},
        ),
        migrations.CreateModel(
            name="SearchLegCondition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("field_name", models.CharField(max_length=200)),
                (
                    "operator",
                    models.CharField(
                        choices=[
                            ("equals", "Equals"),
                            ("contains", "Contains"),
                            ("gte", ">="),
                            ("lte", "<="),
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
                        to="correlations.searchruleleg",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.CreateModel(
            name="SearchFiring",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key_value", models.CharField(default="none", max_length=500)),
                ("finding_count", models.PositiveIntegerField(default=0)),
                ("fired_at", models.DateTimeField(auto_now_add=True)),
                (
                    "incident",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="search_firings",
                        to="incidents.incident",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="search_firings",
                        to="security.organization",
                    ),
                ),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="firings",
                        to="correlations.searchrule",
                    ),
                ),
            ],
            options={"ordering": ["-fired_at"]},
        ),
        migrations.CreateModel(
            name="SearchFinding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_index", models.CharField(max_length=200)),
                ("wazuh_doc_id", models.CharField(max_length=200)),
                ("found_at", models.DateTimeField(auto_now_add=True)),
                (
                    "alert",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="search_findings",
                        to="alerts.alert",
                    ),
                ),
                (
                    "rule",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="findings",
                        to="correlations.searchrule",
                    ),
                ),
            ],
            options={
                "ordering": ["-found_at"],
                "unique_together": {("rule", "source_index", "wazuh_doc_id")},
            },
        ),
    ]
