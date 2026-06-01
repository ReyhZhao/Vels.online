import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("automations", "0003_wazuhactiveresponse"),
        ("incidents", "0024_task_wazuh_response_wazuhresponseexecution"),
    ]

    operations = [
        migrations.AddField(
            model_name="tasktemplateitem",
            name="wazuh_response",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="template_items",
                to="automations.wazuhactiveresponse",
            ),
        ),
    ]
