from django.urls import path

from .views import ExceptionGenerateView, ExceptionRuleDetailView, ExceptionRuleListView

urlpatterns = [
    path("", ExceptionRuleListView.as_view()),
    path("generate/", ExceptionGenerateView.as_view()),
    path("<int:pk>/", ExceptionRuleDetailView.as_view()),
]
