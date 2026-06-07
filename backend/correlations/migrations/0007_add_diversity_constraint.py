from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('correlations', '0006_searchrule_include_agentless'),
    ]

    operations = [
        migrations.AddField(
            model_name='searchruleleg',
            name='distinct_field',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='searchruleleg',
            name='min_distinct',
            field=models.PositiveIntegerField(default=1),
        ),
    ]
