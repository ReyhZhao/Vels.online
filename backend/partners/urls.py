from django.urls import path

from .views import (
    ConnectionDetailView,
    ConnectionListCreateView,
    IntakeInboxCountView,
    IntakeInboxDetailView,
    IntakeInboxListView,
)

urlpatterns = [
    path("connections/", ConnectionListCreateView.as_view()),
    path("connections/<int:pk>/", ConnectionDetailView.as_view()),
    path("intake-inbox/", IntakeInboxListView.as_view()),
    path("intake-inbox/count/", IntakeInboxCountView.as_view()),
    path("intake-inbox/<int:pk>/", IntakeInboxDetailView.as_view()),
]
