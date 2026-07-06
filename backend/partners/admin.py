from django.contrib import admin

from .models import Connection, ConnectionSender


class ConnectionSenderInline(admin.TabularInline):
    model = ConnectionSender
    extra = 1


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "organization", "direction", "active")
    list_filter = ("kind", "direction", "active")
    search_fields = ("name",)
    inlines = [ConnectionSenderInline]
