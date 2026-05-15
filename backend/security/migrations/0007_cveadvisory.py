from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0006_organization_max_routes'),
    ]

    operations = [
        migrations.CreateModel(
            name='CveAdvisory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cve_id', models.CharField(max_length=50)),
                ('platform', models.CharField(max_length=20)),
                ('advisory_url', models.URLField(blank=True, max_length=500, null=True)),
                ('remediation_text', models.TextField(blank=True, null=True)),
                ('fetched_at', models.DateTimeField()),
                ('raw_data', models.JSONField(blank=True, null=True)),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='cveadvisory',
            unique_together={('cve_id', 'platform')},
        ),
    ]
