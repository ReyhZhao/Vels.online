from django.urls import path

from .views import IngressSettingsView, RouteDetailView, RouteListView

urlpatterns = [
    path("settings/", IngressSettingsView.as_view()),
    path("routes/", RouteListView.as_view()),
    path("routes/<str:fqdn>/", RouteDetailView.as_view()),
]
