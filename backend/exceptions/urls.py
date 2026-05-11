from django.urls import path

from .views import (
    ExceptionApproveView,
    ExceptionDisableView,
    ExceptionGenerateView,
    ExceptionRuleDetailView,
    ExceptionRuleListView,
)

urlpatterns = [
    path("", ExceptionRuleListView.as_view()),
    path("generate/", ExceptionGenerateView.as_view()),
    path("<int:pk>/", ExceptionRuleDetailView.as_view()),
    path("<int:pk>/approve/", ExceptionApproveView.as_view()),
    path("<int:pk>/disable/", ExceptionDisableView.as_view()),
]
