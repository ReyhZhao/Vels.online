from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0026_add_correlation_source_kind"),
    ]

    operations = [
        migrations.AlterField(
            model_name="incident",
            name="source_kind",
            field=models.CharField(
                choices=[
                    ("manual", "Manual"),
                    ("api", "API"),
                    ("wazuh_event", "Wazuh Event"),
                    ("vulnerability", "Vulnerability"),
                    ("agent_finding", "Agent Finding"),
                    ("inbound_email", "Inbound Email"),
                    ("workflow", "Workflow"),
                    ("external", "External"),
                    ("correlation", "Correlation Rule"),
                    ("scheduled_search", "Scheduled Search Rule"),
                ],
                default="manual",
                max_length=20,
            ),
        ),
    ]
