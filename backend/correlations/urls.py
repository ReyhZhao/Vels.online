from django.urls import path

from .views import (
    DetectionSuggestionAcceptView,
    DetectionSuggestionDismissView,
    DetectionSuggestionListView,
)

urlpatterns = [
    path("suggestions/", DetectionSuggestionListView.as_view()),
    path("suggestions/<int:pk>/accept/", DetectionSuggestionAcceptView.as_view()),
    path("suggestions/<int:pk>/dismiss/", DetectionSuggestionDismissView.as_view()),
]
