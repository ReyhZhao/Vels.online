from django.urls import path

from .views import SubjectDetailView, SubjectListView

urlpatterns = [
    path("", SubjectListView.as_view()),
    path("<int:pk>/", SubjectDetailView.as_view()),
]
