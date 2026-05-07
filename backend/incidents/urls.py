from django.urls import path

from .views import IncidentDetailView, IncidentListView

urlpatterns = [
    path("", IncidentListView.as_view()),
    path("<int:pk>/", IncidentDetailView.as_view()),
]
