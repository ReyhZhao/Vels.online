from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    PeriodicTaskSerializer,
    PeriodicTaskToggleSerializer,
    TaskResultDetailSerializer,
    TaskResultListSerializer,
)


class TaskHistoryListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        qs = TaskResult.objects.all().order_by("-date_created")

        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status__iexact=status_filter)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(task_name__icontains=search)

        page_size = min(int(request.query_params.get("page_size", 50)), 200)
        page = max(int(request.query_params.get("page", 1)), 1)
        total = qs.count()
        offset = (page - 1) * page_size
        results = qs[offset : offset + page_size]

        return Response({
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": TaskResultListSerializer(results, many=True).data,
        })


class TaskHistoryDetailView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request, task_id):
        try:
            task = TaskResult.objects.get(task_id=task_id)
        except TaskResult.DoesNotExist:
            return Response({"detail": "Not found."}, status=404)
        return Response(TaskResultDetailSerializer(task).data)


class ScheduledTaskListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        tasks = PeriodicTask.objects.select_related("interval", "crontab").order_by("name")
        return Response(PeriodicTaskSerializer(tasks, many=True).data)


class ScheduledTaskDetailView(APIView):
    permission_classes = [IsAdminUser]

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
