from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0006_seed_task_templates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Task",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("state", models.CharField(
                    choices=[
                        ("new", "New"),
                        ("in_progress", "In Progress"),
                        ("done", "Done"),
                        ("cancelled", "Cancelled"),
                    ],
                    default="new",
                    max_length=20,
                )),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("incident", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="tasks",
                    to="incidents.incident",
                )),
                ("template_item", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="tasks",
                    to="incidents.tasktemplateitem",
                )),
                ("assignee", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="assigned_tasks",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["display_order", "created_at"],
            },
        ),
        migrations.CreateModel(
            name="IncidentTemplateApplication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                ("incident", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="template_applications",
                    to="incidents.incident",
                )),
                ("template", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="applications",
                    to="incidents.tasktemplate",
                )),
                ("applied_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="template_applications",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["-applied_at"],
            },
        ),
    ]
