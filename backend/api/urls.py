
from django.urls import include, path

from notifications.views import TestEmailView

from . import views
from .docs_views import ExtendedDocsView
from .public_stats import PublicStatsView
from incidents.views import AssetBulkUpdateView, AssetDetailView, AssetListView, AssetOwnerDetailView, AssetOwnerListView, NatExposureDetailView, NatExposureListView

urlpatterns = [
    path("health/", views.HealthView.as_view()),
    path("me/", views.MeView.as_view()),
    path("public/stats/", PublicStatsView.as_view()),
    path("docs/extended/", ExtendedDocsView.as_view()),
    path("dashboard/overview/", views.DashboardOverviewView.as_view()),
    path("logout/", views.LogoutView.as_view()),
    path("admin/test-email/", TestEmailView.as_view()),
    path("status/", include("status.urls")),
    path("security/", include("security.urls")),
    path("assets/", AssetListView.as_view()),
    path("assets/bulk/", AssetBulkUpdateView.as_view()),
    path("assets/<int:pk>/", AssetDetailView.as_view()),
    path("assets/<int:pk>/owners/", AssetOwnerListView.as_view()),
    path("assets/<int:pk>/owners/<int:contact_pk>/", AssetOwnerDetailView.as_view()),
    path("assets/<int:pk>/nat-exposures/", NatExposureListView.as_view()),
    path("assets/<int:pk>/nat-exposures/<int:nat_pk>/", NatExposureDetailView.as_view()),
    path("incidents/", include("incidents.urls")),
    path("exceptions/", include("exceptions.urls")),
    path("subjects/", include("incidents.subject_urls")),
    path("task-templates/", include("incidents.task_template_urls")),
    path("tasks/", include("incidents.task_urls")),
    path("comments/", include("incidents.comment_urls")),
    path("me/", include("notifications.urls")),
    path("feedback/", include("feedback.urls")),
    path("ingress/", include("ingress.urls")),
    path("signups/", include("signups.urls")),
    path("", include("automations.urls")),
    path("admin/celery/", include("celery_tasks.urls")),
    path("contacts/", include("contacts.urls")),
    path("partners/", include("partners.urls")),
    path("ingest-endpoints/", include("webhook_ingest.urls")),
    path("alerts/", include("alerts.urls")),
    path("correlations/", include("correlations.urls")),
    path("v2/alerts/", include("alerts.urls_v2")),
    path("oncall/", include("oncall.urls")),
    path("hunts/", include("hunts.urls")),
    path("attack-map/", include("attackmap.urls")),
]
