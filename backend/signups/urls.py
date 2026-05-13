from django.urls import path

from .views import (
    SignupRequestApproveView,
    SignupRequestDetailView,
    SignupRequestListView,
    SignupRequestPendingCountView,
    SignupRequestRejectView,
    SignupRequestResendView,
)

urlpatterns = [
    path("", SignupRequestListView.as_view()),
    path("pending-count/", SignupRequestPendingCountView.as_view()),
    path("<int:pk>/", SignupRequestDetailView.as_view()),
    path("<int:pk>/approve/", SignupRequestApproveView.as_view()),
    path("<int:pk>/reject/", SignupRequestRejectView.as_view()),
    path("<int:pk>/resend/", SignupRequestResendView.as_view()),
]
