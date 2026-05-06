import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('security', '0004_work_packages'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='RiskAcceptance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cve_id', models.CharField(max_length=50)),
                ('accepted_at', models.DateTimeField(auto_now_add=True)),
                ('note', models.TextField(blank=True, default='')),
                ('severity', models.CharField(blank=True, default='', max_length=20)),
                ('cvss_score', models.FloatField(blank=True, null=True)),
                ('accepted_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='risk_acceptances',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('org', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='risk_acceptances',
                    to='security.organization',
                )),
            ],
        ),
        migrations.AlterUniqueTogether(
            name='riskacceptance',
            unique_together={('org', 'cve_id')},
        ),
    ]
