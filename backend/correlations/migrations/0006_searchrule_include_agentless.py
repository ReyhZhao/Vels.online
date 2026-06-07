from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('correlations', '0005_add_system_search_rules'),
    ]

    operations = [
        migrations.AddField(
            model_name='searchrule',
            name='include_agentless',
            field=models.BooleanField(default=False),
        ),
    ]
