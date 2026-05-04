from django.db import models


class MonitorVisibility(models.Model):
    monitor_id = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=255)
    is_visible = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "monitor visibilities"

    def __str__(self):
        return self.name
