from django.apps import AppConfig


class IncidentsConfig(AppConfig):
    name = "incidents"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        import incidents.signals  # noqa: F401
