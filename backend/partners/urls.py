from django.urls import path

from .views import ConnectionDetailView, ConnectionListCreateView

urlpatterns = [
    path("connections/", ConnectionListCreateView.as_view()),
    path("connections/<int:pk>/", ConnectionDetailView.as_view()),
]
