from django.urls import path

from .views import IncidentDetailView, IncidentListView, IncidentTransitionView

urlpatterns = [
    path("", IncidentListView.as_view()),
    path("<int:pk>/", IncidentDetailView.as_view()),
    path("<int:pk>/transition/", IncidentTransitionView.as_view()),
]
