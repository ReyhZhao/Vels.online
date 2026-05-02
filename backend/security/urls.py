from django.urls import path

from .views import (
    AgentEventsView,
    AgentListView,
    AgentVulnerabilitiesView,
    DashboardView,
    EnrollmentView,
    OrganizationListView,
    SecurityRefreshView,
)

urlpatterns = [
    path("organizations/", OrganizationListView.as_view()),
    path("agents/", AgentListView.as_view()),
    path("agents/<str:agent_id>/events/", AgentEventsView.as_view()),
    path("agents/<str:agent_id>/vulnerabilities/", AgentVulnerabilitiesView.as_view()),
    path("dashboard/", DashboardView.as_view()),
    path("dashboard/refresh/", SecurityRefreshView.as_view()),
    path("enrollment/", EnrollmentView.as_view()),
]
