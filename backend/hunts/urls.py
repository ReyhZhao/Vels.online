from django.urls import path

from .views import (
    HuntBeginView,
    HuntCancelView,
    HuntConfirmIncidentView,
    HuntDetailView,
    HuntListCreateView,
    HuntStreamView,
    HuntTurnView,
)

urlpatterns = [
    path("", HuntListCreateView.as_view()),
    path("<uuid:hunt_id>/", HuntDetailView.as_view()),
    path("<uuid:hunt_id>/turn/", HuntTurnView.as_view()),
    path("<uuid:hunt_id>/begin/", HuntBeginView.as_view()),
    path("<uuid:hunt_id>/cancel/", HuntCancelView.as_view()),
    path("<uuid:hunt_id>/confirm-incident/", HuntConfirmIncidentView.as_view()),
    path("<uuid:hunt_id>/stream/", HuntStreamView.as_view()),
]
