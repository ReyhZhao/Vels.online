from django.urls import path

from . import views

urlpatterns = [
    path("organizations/", views.organizations_view),
    path("agents/", views.agents_view),
    path("dashboard/", views.dashboard_view),
    path("dashboard/refresh/", views.refresh_view),
    path("enrollment/", views.enrollment_view),
]
