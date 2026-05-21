from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("contacts", "0002_assetowner"),
        ("incidents", "0017_asset_is_active_last_seen_at"),
    ]

    operations = [
        migrations.CreateModel(
            name="IncidentContact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(
                    choices=[("notified", "Notified"), ("questioned", "Questioned")],
                    default="notified",
                    max_length=20,
                )),
                ("message", models.TextField(blank=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "contact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incident_contacts",
                        to="contacts.contact",
                    ),
                ),
                (
                    "incident",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incident_contacts",
                        to="incidents.incident",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
                "unique_together": {("incident", "contact")},
            },
        ),
    ]
