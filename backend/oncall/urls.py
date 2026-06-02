from django.urls import path

from .views import ShiftBlockDetailView, ShiftBlockListView, StaffProfileView

urlpatterns = [
    path("me/profile/", StaffProfileView.as_view()),
    path("blocks/", ShiftBlockListView.as_view()),
    path("blocks/<int:pk>/", ShiftBlockDetailView.as_view()),
]
