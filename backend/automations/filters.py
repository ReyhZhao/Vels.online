import django_filters

from .models import Automation


class AutomationFilterSet(django_filters.FilterSet):
    include_archived = django_filters.BooleanFilter(method="filter_include_archived")

    class Meta:
        model = Automation
        fields = []

    def filter_include_archived(self, qs, name, value):
        # Filtering is handled in the view's get_queryset() to correctly
        # exclude archived by default when the param is absent.
        return qs
