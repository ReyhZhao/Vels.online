import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("security", "0005_riskacceptance"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Incident",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_kind", models.CharField(
                    choices=[
                        ("manual", "Manual"),
                        ("api", "API"),
                        ("wazuh_event", "Wazuh Event"),
                        ("vulnerability", "Vulnerability"),
                        ("agent_finding", "Agent Finding"),
                    ],
                    default="manual",
                    max_length=20,
                )),
                ("source_ref", models.JSONField(blank=True, default=dict)),
                ("display_id", models.CharField(blank=True, max_length=20, unique=True)),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("severity", models.CharField(
                    choices=[
                        ("critical", "Critical"),
                        ("high", "High"),
                        ("medium", "Medium"),
                        ("low", "Low"),
                        ("info", "Info"),
                    ],
                    default="medium",
                    max_length=10,
                )),
                ("tlp", models.CharField(
                    choices=[
                        ("white", "TLP:WHITE"),
                        ("green", "TLP:GREEN"),
                        ("amber", "TLP:AMBER"),
                        ("red", "TLP:RED"),
                    ],
                    default="amber",
                    max_length=10,
                )),
                ("pap", models.CharField(
                    choices=[
                        ("white", "PAP:WHITE"),
                        ("green", "PAP:GREEN"),
                        ("amber", "PAP:AMBER"),
                        ("red", "PAP:RED"),
                    ],
                    default="amber",
                    max_length=10,
                )),
                ("state", models.CharField(
                    choices=[("new", "New")],
                    default="new",
                    max_length=20,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("assignee", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="assigned_incidents",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_incidents",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="incidents",
                    to="security.organization",
                )),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="IncidentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(max_length=50)),
                ("payload", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="incident_events",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("incident", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="events",
                    to="incidents.incident",
                )),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="incidentevent",
            index=models.Index(fields=["incident", "created_at"], name="incidents_i_inciden_idx"),
        ),
    ]
