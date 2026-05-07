import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("incidents", "0004_seed_subjects"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TaskTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("is_auto_apply", models.BooleanField(default=False)),
                ("archived", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="created_task_templates",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("subject", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="task_templates",
                    to="incidents.subject",
                )),
            ],
            options={"ordering": ["subject__name", "name"]},
        ),
        migrations.CreateModel(
            name="TaskTemplateItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, default="")),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("template", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="items",
                    to="incidents.tasktemplate",
                )),
            ],
            options={"ordering": ["display_order", "id"]},
        ),
    ]
