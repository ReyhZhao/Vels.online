from django.urls import path

from .views import monitor_detail_view, monitors_view, refresh_view, status_view

urlpatterns = [
    path("", status_view),
    path("refresh/", refresh_view),
    path("monitors/", monitors_view),
    path("monitors/<str:monitor_id>/", monitor_detail_view),
]
