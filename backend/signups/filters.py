import django_filters

from .models import SignupRequest


class SignupRequestFilterSet(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="exact")

    class Meta:
        model = SignupRequest
        fields = []
