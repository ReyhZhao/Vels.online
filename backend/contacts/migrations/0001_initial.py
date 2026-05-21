from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("security", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Contact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("email", models.EmailField(max_length=254)),
                ("job_title", models.CharField(blank=True, max_length=255)),
                ("department", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "organisation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="contacts",
                        to="security.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "unique_together": {("organisation", "email")},
            },
        ),
    ]
