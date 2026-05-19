import django_filters

from .models import ExceptionRule


class ExceptionRuleFilterSet(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")
    organisation = django_filters.CharFilter(field_name="organisation__slug", lookup_expr="exact")
    incident = django_filters.CharFilter(field_name="incident__display_id", lookup_expr="exact")

    class Meta:
        model = ExceptionRule
        fields = []
