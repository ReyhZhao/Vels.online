from django.urls import path

from .views import MonitorDetailView, MonitorListView, StatusRefreshView, StatusView

urlpatterns = [
    path("", StatusView.as_view()),
    path("refresh/", StatusRefreshView.as_view()),
    path("monitors/", MonitorListView.as_view()),
    path("monitors/<str:monitor_id>/", MonitorDetailView.as_view()),
]
