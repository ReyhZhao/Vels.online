from django.urls import path

from .views import (
    CapturedPayloadDetailView,
    CapturedPayloadListView,
    IngestEndpointActivateView,
    IngestEndpointDetailView,
    IngestEndpointDryRunView,
    IngestEndpointListCreateView,
    IngestEndpointPauseView,
    IngestEndpointReplayView,
    IngestEndpointRotateView,
)

urlpatterns = [
    path("endpoints/", IngestEndpointListCreateView.as_view()),
    path("endpoints/<int:pk>/", IngestEndpointDetailView.as_view()),
    path("endpoints/<int:pk>/rotate/", IngestEndpointRotateView.as_view()),
    path("endpoints/<int:pk>/activate/", IngestEndpointActivateView.as_view()),
    path("endpoints/<int:pk>/pause/", IngestEndpointPauseView.as_view()),
    path("endpoints/<int:pk>/dry-run/", IngestEndpointDryRunView.as_view()),
    path("endpoints/<int:pk>/captured/", CapturedPayloadListView.as_view()),
    path("endpoints/<int:pk>/replay/", IngestEndpointReplayView.as_view()),
    path("captured/<int:pk>/", CapturedPayloadDetailView.as_view()),
]
