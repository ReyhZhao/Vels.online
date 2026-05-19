from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import TaskHistoryFilterSet
from .serializers import (
    PeriodicTaskSerializer,
    PeriodicTaskToggleSerializer,
    TaskResultDetailSerializer,
    TaskResultListSerializer,
)


class TaskHistoryListView(ListAPIView):
    permission_classes = [IsAdminUser]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TaskHistoryFilterSet
    serializer_class = TaskResultListSerializer

    def get_queryset(self):
        return TaskResult.objects.all().order_by("-date_created")

    @extend_schema(operation_id="admin_celery_history_list", responses=TaskResultListSerializer)
    def get(self, request, *args, **kwargs):
        return self.list(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page_size = min(int(request.query_params.get("page_size", 50)), 200)
        page = max(int(request.query_params.get("page", 1)), 1)
        total = qs.count()
        offset = (page - 1) * page_size
        results = qs[offset: offset + page_size]
        return Response({
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": self.get_serializer(results, many=True).data,
        })


class TaskHistoryDetailView(APIView):
    permission_classes = [IsAdminUser]

    @extend_schema(operation_id="admin_celery_history_detail", responses=TaskResultDetailSerializer)
    def get(self, request, task_id):
        try:
            task = TaskResult.objects.get(task_id=task_id)
        except TaskResult.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)
        return Response(TaskResultDetailSerializer(task).data)


class ScheduledTaskListView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = PeriodicTaskSerializer

    def get(self, request):
        tasks = PeriodicTask.objects.select_related("interval", "crontab").order_by("name")
        return Response(PeriodicTaskSerializer(tasks, many=True).data)


class ScheduledTaskDetailView(APIView):
    permission_classes = [IsAdminUser]
    serializer_class = PeriodicTaskToggleSerializer

    def patch(self, request, pk):
        try:
            task = PeriodicTask.objects.get(pk=pk)
        except PeriodicTask.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)

        serializer = PeriodicTaskToggleSerializer(task, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
        serializer.save()
        return Response(PeriodicTaskSerializer(task).data)


class ScheduledTaskRunView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            periodic_task = PeriodicTask.objects.get(pk=pk)
        except PeriodicTask.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)

        from celery import current_app
        result = current_app.send_task(periodic_task.task)
        return Response({"task_id": result.id})
