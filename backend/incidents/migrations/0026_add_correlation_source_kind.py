from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0025_tasktemplateitem_wazuh_response"),
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
                ],
                default="manual",
                max_length=20,
            ),
        ),
    ]
