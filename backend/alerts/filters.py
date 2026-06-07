import django_filters
from django.db.models import Q

from .models import Alert


class AlertFilterSet(django_filters.FilterSet):
    state = django_filters.CharFilter(field_name='state', lookup_expr='exact')
    severity = django_filters.CharFilter(field_name='severity', lookup_expr='exact')
    source_kind = django_filters.CharFilter(field_name='source_kind', lookup_expr='exact')
    date_from = django_filters.DateFilter(field_name='created_at__date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='created_at__date', lookup_expr='lte')
    exclude_state = django_filters.CharFilter(method='filter_exclude_state')
    has_incident = django_filters.CharFilter(method='filter_has_incident')
    search = django_filters.CharFilter(method='filter_search')

    class Meta:
        model = Alert
        fields = []

    def filter_exclude_state(self, queryset, name, value):
        states = [s.strip() for s in value.split(',') if s.strip()]
        return queryset.exclude(state__in=states)

    def filter_has_incident(self, queryset, name, value):
        if value.lower() in ('true', '1', 'yes'):
            return queryset.filter(incident__isnull=False)
        if value.lower() in ('false', '0', 'no'):
            return queryset.filter(incident__isnull=True)
        return queryset

    def filter_search(self, queryset, name, value):
        return queryset.filter(
            Q(title__icontains=value) | Q(description__icontains=value)
        )
