from django.urls import path

from .views import AlertBulkPromotePreviewView, AlertBulkPromoteView, AlertDetailView, AlertListIngestView

urlpatterns = [
    path("", AlertListIngestView.as_view(), name="alert-list"),
    path("bulk-promote/preview/", AlertBulkPromotePreviewView.as_view(), name="alert-bulk-promote-preview"),
    path("bulk-promote/", AlertBulkPromoteView.as_view(), name="alert-bulk-promote"),
    path("<str:display_id>/", AlertDetailView.as_view(), name="alert-detail"),
]
