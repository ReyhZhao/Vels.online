from django.urls import path

from .views import TaskCommentListView, TaskDetailView

urlpatterns = [
    path("<int:pk>/", TaskDetailView.as_view()),
    path("<int:pk>/comments/", TaskCommentListView.as_view()),
]
