from django.urls import path

from .views import AutomationDetailView, AutomationListView, SemaphoreTemplatesView

urlpatterns = [
    path("automations/", AutomationListView.as_view()),
    path("automations/<int:pk>/", AutomationDetailView.as_view()),
    path("semaphore/templates/", SemaphoreTemplatesView.as_view()),
]
