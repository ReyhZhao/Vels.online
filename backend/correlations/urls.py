from django.urls import path

from .views import (
    CorrelationCatalogView,
    CorrelationRuleDetailView,
    CorrelationRuleListView,
    DetectionSuggestionAcceptView,
    DetectionSuggestionDismissView,
    DetectionSuggestionListView,
)

urlpatterns = [
    path("suggestions/", DetectionSuggestionListView.as_view()),
    path("suggestions/<int:pk>/accept/", DetectionSuggestionAcceptView.as_view()),
    path("suggestions/<int:pk>/dismiss/", DetectionSuggestionDismissView.as_view()),
    path("rules/", CorrelationRuleListView.as_view()),
    path("rules/<int:pk>/", CorrelationRuleDetailView.as_view()),
    path("catalog/", CorrelationCatalogView.as_view()),
]
