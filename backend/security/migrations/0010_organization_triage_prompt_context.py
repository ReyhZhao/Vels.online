from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0009_organization_triage_fp_threshold'),
    ]

    operations = [
        migrations.AddField(
            model_name='organization',
            name='triage_prompt_context',
            field=models.TextField(blank=True, null=True),
        ),
    ]
