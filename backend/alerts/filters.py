import django_filters

from .models import Alert


class AlertFilterSet(django_filters.FilterSet):
    state = django_filters.CharFilter(field_name='state', lookup_expr='exact')
    severity = django_filters.CharFilter(field_name='severity', lookup_expr='exact')
    source_kind = django_filters.CharFilter(field_name='source_kind', lookup_expr='exact')
    date_from = django_filters.DateFilter(field_name='created_at__date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='created_at__date', lookup_expr='lte')

    class Meta:
        model = Alert
        fields = []
