from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("security", "0017_organization_latitude_organization_longitude"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="internal_ip_ranges",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="organization",
            name="owned_domains",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
