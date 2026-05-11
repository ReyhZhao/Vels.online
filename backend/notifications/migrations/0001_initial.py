import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("incidents", "0010_attachment"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="NotificationPreferences",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("email_assignment", models.BooleanField(default=True)),
                ("inapp_assignment", models.BooleanField(default=True)),
                ("email_delegation", models.BooleanField(default=True)),
                ("inapp_delegation", models.BooleanField(default=True)),
                ("email_comment", models.BooleanField(default=True)),
                ("inapp_comment", models.BooleanField(default=True)),
                ("email_state_change", models.BooleanField(default=True)),
                ("inapp_state_change", models.BooleanField(default=True)),
                ("email_incident_alert", models.BooleanField(default=True)),
                ("inapp_incident_alert", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_preferences",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("assignment", "Assignment"),
                            ("delegation", "Delegation"),
                            ("comment", "Comment"),
                            ("state_change", "State Change"),
                            ("incident_alert", "Incident Alert"),
                        ],
                        max_length=30,
                    ),
                ),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("email_sent_at", models.DateTimeField(blank=True, null=True)),
                (
                    "incident",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to="incidents.incident",
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="notifications",
                        to="incidents.task",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["recipient", "read_at"], name="notif_recipient_read_idx"),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                fields=["recipient", "incident", "email_sent_at"],
                name="notif_recipient_incident_email_idx",
            ),
        ),
    ]
