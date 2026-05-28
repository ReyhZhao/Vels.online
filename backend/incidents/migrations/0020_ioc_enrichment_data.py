from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('incidents', '0019_comment_kind_ai_task_summary'),
    ]

    operations = [
        migrations.AddField(
            model_name='ioc',
            name='enrichment_data',
            field=models.JSONField(default=dict),
        ),
    ]
