from django.urls import path

from .memory.views import SubjectCorrectionsView
from .views import SubjectDetailView, SubjectListView

urlpatterns = [
    path("", SubjectListView.as_view()),
    path("<int:pk>/", SubjectDetailView.as_view()),
    path("<int:pk>/corrections/", SubjectCorrectionsView.as_view()),
]
