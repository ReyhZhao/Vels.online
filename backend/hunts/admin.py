from django.contrib import admin

from .models import Hunt, HuntEvent, HuntFinding


@admin.register(Hunt)
class HuntAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "status", "owner", "scope_all_orgs", "created_at")
    list_filter = ("status", "scope_all_orgs", "seed_kind")
    search_fields = ("id", "title", "seed_text", "seed_url")


@admin.register(HuntFinding)
class HuntFindingAdmin(admin.ModelAdmin):
    list_display = ("id", "hunt", "organization", "lens", "wazuh_doc_id", "materialised_incident")
    list_filter = ("lens",)


@admin.register(HuntEvent)
class HuntEventAdmin(admin.ModelAdmin):
    list_display = ("hunt", "seq", "turn", "type", "created_at")
    list_filter = ("type",)
