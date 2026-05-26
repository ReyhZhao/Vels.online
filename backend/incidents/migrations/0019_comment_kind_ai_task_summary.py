from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('incidents', '0018_incident_duplicate_of'),
    ]

    operations = [
        migrations.AlterField(
            model_name='comment',
            name='kind',
            field=models.CharField(
                choices=[
                    ('user', 'User'),
                    ('ai_triage', 'AI Triage'),
                    ('system', 'System'),
                    ('ai_task_summary', 'AI Task Summary'),
                ],
                default='user',
                max_length=20,
            ),
        ),
    ]
