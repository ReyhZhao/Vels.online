from django.contrib import admin

from .models import MonitorVisibility


@admin.register(MonitorVisibility)
class MonitorVisibilityAdmin(admin.ModelAdmin):
    list_display = ("monitor_id", "name", "is_visible")
    list_editable = ("is_visible",)
