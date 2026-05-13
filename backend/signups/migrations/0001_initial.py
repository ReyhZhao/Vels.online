import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SignupRequest",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("email", models.EmailField(max_length=254)),
                ("full_name", models.CharField(max_length=255)),
                ("org_name", models.CharField(max_length=255)),
                ("intended_use", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("approved", "Approved"),
                            ("rejected", "Rejected"),
                            ("expired", "Expired"),
                            ("completed", "Completed"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("approved_org_name", models.CharField(blank=True, max_length=255)),
                ("org_slug", models.SlugField(blank=True, max_length=255)),
                ("authentik_group_pk", models.CharField(blank=True, max_length=255)),
                ("invite_token", models.UUIDField(blank=True, null=True)),
                ("invite_expires_at", models.DateTimeField(blank=True, null=True)),
                ("rejection_reason", models.CharField(blank=True, max_length=255)),
                ("rejection_note", models.TextField(blank=True)),
                ("send_rejection_email", models.BooleanField(default=True)),
                ("submitted_at", models.DateTimeField(auto_now_add=True)),
                ("actioned_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-submitted_at"],
            },
        ),
    ]
