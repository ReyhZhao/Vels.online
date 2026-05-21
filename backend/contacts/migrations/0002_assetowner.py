from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("contacts", "0001_initial"),
        ("incidents", "0017_asset_is_active_last_seen_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="AssetOwner",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "contact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asset_ownerships",
                        to="contacts.contact",
                    ),
                ),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="asset_ownerships",
                        to="incidents.asset",
                    ),
                ),
            ],
            options={
                "unique_together": {("contact", "asset")},
            },
        ),
    ]
