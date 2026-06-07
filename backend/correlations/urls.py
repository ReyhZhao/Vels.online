from django.urls import path

from .views import (
    CorrelationCatalogView,
    CorrelationDraftView,
    CorrelationRuleDetailView,
    CorrelationRuleListView,
    DetectionSuggestionAcceptView,
    DetectionSuggestionDismissView,
    DetectionSuggestionListView,
    OrgSystemRuleMuteView,
    OrgSystemRulesView,
    OrgSystemSearchRuleMuteView,
    OrgSystemSearchRulesView,
    SearchCatalogView,
    SearchRuleDraftView,
    SearchRuleDetailView,
    SearchRuleListView,
    SearchRuleRunNowView,
)

urlpatterns = [
    path("suggestions/", DetectionSuggestionListView.as_view()),
    path("suggestions/<int:pk>/accept/", DetectionSuggestionAcceptView.as_view()),
    path("suggestions/<int:pk>/dismiss/", DetectionSuggestionDismissView.as_view()),
    path("rules/", CorrelationRuleListView.as_view()),
    path("rules/<int:pk>/", CorrelationRuleDetailView.as_view()),
    path("catalog/", CorrelationCatalogView.as_view()),
    path("draft/", CorrelationDraftView.as_view()),
    path("org-system-rules/", OrgSystemRulesView.as_view()),
    path("org-system-rules/<int:pk>/mute/", OrgSystemRuleMuteView.as_view()),
    path("search-draft/", SearchRuleDraftView.as_view()),
    path("search-rules/", SearchRuleListView.as_view()),
    path("search-rules/<int:pk>/", SearchRuleDetailView.as_view()),
    path("search-rules/<int:pk>/run/", SearchRuleRunNowView.as_view()),
    path("search-catalog/", SearchCatalogView.as_view()),
    path("org-system-search-rules/", OrgSystemSearchRulesView.as_view()),
    path("org-system-search-rules/<int:pk>/mute/", OrgSystemSearchRuleMuteView.as_view()),
]
