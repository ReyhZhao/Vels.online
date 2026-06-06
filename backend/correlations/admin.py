from django.contrib import admin
from django.utils import timezone
from datetime import timedelta

from .models import SearchFiring, SearchFinding, SearchLegCondition, SearchRule, SearchRuleLeg


class SearchLegConditionInline(admin.TabularInline):
    model = SearchLegCondition
    extra = 0
    fields = ["field_name", "operator", "value"]


class SearchRuleLegInline(admin.StackedInline):
    model = SearchRuleLeg
    extra = 0
    show_change_link = True
    fields = ["display_order"]


@admin.register(SearchRule)
class SearchRuleAdmin(admin.ModelAdmin):
    list_display = [
        "name", "organization", "severity", "interval_minutes",
        "enabled", "last_run_at", "next_run_at", "total_run_count",
    ]
    list_filter = ["enabled", "severity", "organization"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at", "last_run_at", "next_run_at", "total_run_count"]
    inlines = [SearchRuleLegInline]
    actions = ["run_now"]

    def _periodic_task(self, obj):
        try:
            from django_celery_beat.models import PeriodicTask
            return PeriodicTask.objects.get(name=f"search_rule_{obj.id}")
        except Exception:
            return None

    @admin.display(description="Last run")
    def last_run_at(self, obj):
        pt = self._periodic_task(obj)
        return pt.last_run_at if pt else "—"

    @admin.display(description="Next run")
    def next_run_at(self, obj):
        pt = self._periodic_task(obj)
        if pt and pt.last_run_at and pt.interval:
            return pt.last_run_at + timedelta(minutes=pt.interval.every)
        return "—"

    @admin.display(description="Total runs")
    def total_run_count(self, obj):
        pt = self._periodic_task(obj)
        return pt.total_run_count if pt else 0

    @admin.action(description="Run selected search rules now")
    def run_now(self, request, queryset):
        from correlations.tasks import run_scheduled_search_rule
        count = 0
        for rule in queryset:
            run_scheduled_search_rule.delay(rule.id)
            count += 1
        self.message_user(request, f"Enqueued {count} rule run(s).")

    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/run/",
                self.admin_site.admin_view(self._run_now_view),
                name="correlations_searchrule_run",
            ),
        ]
        return custom + urls

    def _run_now_view(self, request, pk):
        from django.http import HttpResponseRedirect
        from django.urls import reverse
        from correlations.tasks import run_scheduled_search_rule
        try:
            rule = SearchRule.objects.get(pk=pk)
            run_scheduled_search_rule.delay(rule.id)
            self.message_user(request, f"Enqueued run for '{rule.name}'.")
        except SearchRule.DoesNotExist:
            self.message_user(request, "Rule not found.", level="error")
        return HttpResponseRedirect(
            reverse("admin:correlations_searchrule_changelist")
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["run_now_url"] = f"{object_id}/run/"
        return super().change_view(request, object_id, form_url, extra_context)


@admin.register(SearchFiring)
class SearchFiringAdmin(admin.ModelAdmin):
    list_display = ["rule", "organization", "finding_count", "fired_at", "incident"]
    list_filter = ["rule", "organization"]
    readonly_fields = ["fired_at"]
