import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automations", "0003_wazuhactiveresponse"),
        ("incidents", "0023_add_asset_is_permanent"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="wazuh_response",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tasks",
                to="automations.wazuhactiveresponse",
            ),
        ),
        migrations.AlterField(
            model_name="task",
            name="task_type",
            field=models.CharField(
                choices=[
                    ("manual", "Manual"),
                    ("automated", "Automated"),
                    ("wazuh_response", "Wazuh Response"),
                ],
                default="manual",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="WazuhResponseExecution",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("agent_ids", models.JSONField(default=list)),
                ("resolved_args", models.TextField(blank=True, default="")),
                ("timeout_used", models.PositiveIntegerField(default=0)),
                ("wazuh_status_code", models.IntegerField(blank=True, null=True)),
                ("wazuh_response_body", models.JSONField(default=dict)),
                ("executed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "executed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wazuh_executions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "incident",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wazuh_executions",
                        to="incidents.incident",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="wazuh_executions",
                        to="incidents.task",
                    ),
                ),
                (
                    "wazuh_response",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="executions",
                        to="automations.wazuhactiveresponse",
                    ),
                ),
            ],
            options={
                "ordering": ["-executed_at"],
            },
        ),
    ]
