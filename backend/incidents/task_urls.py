from django.urls import path

from .views import TaskDetailView

urlpatterns = [
    path("<int:pk>/", TaskDetailView.as_view()),
]
