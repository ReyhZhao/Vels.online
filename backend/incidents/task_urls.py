from django.urls import path

from .views import TaskCommentListView, TaskDetailView, TaskListView, TaskRunView

urlpatterns = [
    path("", TaskListView.as_view()),
    path("<int:pk>/", TaskDetailView.as_view()),
    path("<int:pk>/run/", TaskRunView.as_view()),
    path("<int:pk>/comments/", TaskCommentListView.as_view()),
]
