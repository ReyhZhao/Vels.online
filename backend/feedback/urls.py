from django.urls import path
from .views import CreateGithubIssueView

urlpatterns = [
    path("issue/", CreateGithubIssueView.as_view()),
]
