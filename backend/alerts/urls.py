from django.urls import path

from .views import AlertBulkPromoteView, AlertDetailView, AlertListIngestView

urlpatterns = [
    path("", AlertListIngestView.as_view(), name="alert-list"),
    path("bulk-promote/", AlertBulkPromoteView.as_view(), name="alert-bulk-promote"),
    path("<str:display_id>/", AlertDetailView.as_view(), name="alert-detail"),
]
