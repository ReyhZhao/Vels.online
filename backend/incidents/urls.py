from django.urls import path

from .views import (
    ApplyTemplateView,
    IncidentCommentListView,
    IncidentDetailView,
    IncidentListView,
    IncidentTaskListView,
    IncidentTransitionView,
    PromoteView,
)

urlpatterns = [
    path("", IncidentListView.as_view()),
    path("promote/", PromoteView.as_view()),
    path("<int:pk>/", IncidentDetailView.as_view()),
    path("<int:pk>/transition/", IncidentTransitionView.as_view()),
    path("<int:pk>/tasks/", IncidentTaskListView.as_view()),
    path("<int:pk>/apply-template/", ApplyTemplateView.as_view()),
    path("<int:pk>/comments/", IncidentCommentListView.as_view()),
]
