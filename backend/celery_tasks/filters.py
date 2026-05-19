import django_filters
from django_celery_results.models import TaskResult


class TaskHistoryFilterSet(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="iexact")
    search = django_filters.CharFilter(field_name="task_name", lookup_expr="icontains")

    class Meta:
        model = TaskResult
        fields = []
