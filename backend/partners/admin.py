from django.contrib import admin

from .models import Connection, ConnectionSender, IntakeInboxMessage


class ConnectionSenderInline(admin.TabularInline):
    model = ConnectionSender
    extra = 1


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "organization", "direction", "active")
    list_filter = ("kind", "direction", "active")
    search_fields = ("name",)
    inlines = [ConnectionSenderInline]


@admin.register(IntakeInboxMessage)
class IntakeInboxMessageAdmin(admin.ModelAdmin):
    list_display = ("sender", "subject", "drop_reason", "received_at")
    list_filter = ("drop_reason",)
    search_fields = ("sender", "subject")
