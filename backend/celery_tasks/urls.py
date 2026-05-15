from django.urls import path

from .views import (
    ScheduledTaskDetailView,
    ScheduledTaskListView,
    ScheduledTaskRunView,
    TaskHistoryDetailView,
    TaskHistoryListView,
)

urlpatterns = [
    path("history/", TaskHistoryListView.as_view()),
    path("history/<str:task_id>/", TaskHistoryDetailView.as_view()),
    path("scheduled/", ScheduledTaskListView.as_view()),
    path("scheduled/<int:pk>/", ScheduledTaskDetailView.as_view()),
    path("scheduled/<int:pk>/run/", ScheduledTaskRunView.as_view()),
]
