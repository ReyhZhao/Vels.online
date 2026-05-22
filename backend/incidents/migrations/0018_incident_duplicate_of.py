import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0017_asset_is_active_last_seen_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="incident",
            name="duplicate_of",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="duplicates",
                to="incidents.incident",
            ),
        ),
    ]
