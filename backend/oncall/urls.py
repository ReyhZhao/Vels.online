from django.urls import path

from .views import (
    CurrentOnCallView,
    OnCallScheduleMonthView,
    OnCallScheduleWeekView,
    RotationTemplateView,
    ShiftBlockDetailView,
    ShiftBlockListView,
    ShiftOverrideActionView,
    ShiftOverrideListView,
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
    path("overrides/", ShiftOverrideListView.as_view()),
    path("overrides/<int:pk>/<str:action>/", ShiftOverrideActionView.as_view()),
]
