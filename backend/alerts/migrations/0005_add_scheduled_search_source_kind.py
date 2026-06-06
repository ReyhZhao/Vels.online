from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0004_add_alert_entity"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="source_kind",
            field=models.CharField(
                choices=[
                    ("wazuh_event", "Wazuh Event"),
                    ("vulnerability", "Vulnerability"),
                    ("agent_finding", "Agent Finding"),
                    ("api", "API"),
                    ("inbound_email", "Inbound Email"),
                    ("workflow", "Workflow"),
                    ("external", "External"),
                    ("scheduled_search", "Scheduled Search Rule"),
                ],
                max_length=20,
            ),
        ),
    ]
