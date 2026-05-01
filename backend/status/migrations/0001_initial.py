from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="MonitorVisibility",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("monitor_id", models.CharField(max_length=50, unique=True)),
                ("name", models.CharField(max_length=255)),
                ("is_visible", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name_plural": "monitor visibilities",
            },
        ),
    ]
