import django_filters

from .models import Route


class RouteFilterSet(django_filters.FilterSet):
    org = django_filters.CharFilter(method="filter_org")

    class Meta:
        model = Route
        fields = []

    def filter_org(self, qs, name, value):
        # Org resolution and auth-scoping happen in get_queryset(); this method
        # exists solely so Swagger picks up the `org` query parameter.
        return qs
