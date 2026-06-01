from django.urls import path

from .views import (
    AutomationDetailView,
    AutomationListView,
    SemaphoreTemplatesView,
    WazuhResponseDetailView,
    WazuhResponseListView,
)

urlpatterns = [
    path("automations/", AutomationListView.as_view()),
    path("automations/<int:pk>/", AutomationDetailView.as_view()),
    path("semaphore/templates/", SemaphoreTemplatesView.as_view()),
    path("wazuh-responses/", WazuhResponseListView.as_view()),
    path("wazuh-responses/<int:pk>/", WazuhResponseDetailView.as_view()),
]
