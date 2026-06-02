from django.urls import path

from .views import StaffProfileView

urlpatterns = [
    path("me/profile/", StaffProfileView.as_view()),
]
