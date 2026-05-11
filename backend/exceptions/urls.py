from django.urls import path

from .views import ExceptionRuleDetailView, ExceptionRuleListView

urlpatterns = [
    path("", ExceptionRuleListView.as_view()),
    path("<int:pk>/", ExceptionRuleDetailView.as_view()),
]
