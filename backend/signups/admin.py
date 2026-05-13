from django.contrib import admin

from .models import SignupRequest


@admin.register(SignupRequest)
class SignupRequestAdmin(admin.ModelAdmin):
    list_display = ["email", "full_name", "org_name", "status", "submitted_at", "actioned_at"]
    list_filter = ["status"]
    search_fields = ["email", "full_name", "org_name"]
    readonly_fields = ["submitted_at", "actioned_at", "invite_token", "invite_expires_at"]
    ordering = ["-submitted_at"]
