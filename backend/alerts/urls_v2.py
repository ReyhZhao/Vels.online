from django.urls import path

from .views import AlertListIngestV2View

urlpatterns = [
    path("", AlertListIngestV2View.as_view(), name="alert-ingest-v2"),
]
