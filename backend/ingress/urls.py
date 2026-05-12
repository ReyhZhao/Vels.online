from django.urls import path

from .views import IngressSettingsView, RouteDetailView, RouteListView, RouteReportsView, RouteSettingsView

urlpatterns = [
    path("settings/", IngressSettingsView.as_view()),
    path("routes/", RouteListView.as_view()),
    path("routes/<str:fqdn>/settings/", RouteSettingsView.as_view()),
    path("routes/<str:fqdn>/reports/", RouteReportsView.as_view()),
    path("routes/<str:fqdn>/", RouteDetailView.as_view()),
]
