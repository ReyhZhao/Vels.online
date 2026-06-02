from django.urls import path

from .views import (
    CurrentOnCallView,
    OnCallScheduleMonthView,
    OnCallScheduleWeekView,
    RotationTemplateView,
    ShiftBlockDetailView,
    ShiftBlockListView,
    StaffProfileView,
)

urlpatterns = [
    path("me/profile/", StaffProfileView.as_view()),
    path("blocks/", ShiftBlockListView.as_view()),
    path("blocks/<int:pk>/", ShiftBlockDetailView.as_view()),
    path("template/", RotationTemplateView.as_view()),
    path("current/", CurrentOnCallView.as_view()),
    path("schedule/", OnCallScheduleWeekView.as_view()),
    path("schedule/month/", OnCallScheduleMonthView.as_view()),
]
