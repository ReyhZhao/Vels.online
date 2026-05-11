
from django.urls import include, path

from blog.urls import router as blog_router

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view()),
    path("me/", views.MeView.as_view()),
    path("logout/", views.LogoutView.as_view()),
    path("status/", include("status.urls")),
    path("security/", include("security.urls")),
    path("incidents/", include("incidents.urls")),
    path("exceptions/", include("exceptions.urls")),
    path("subjects/", include("incidents.subject_urls")),
    path("task-templates/", include("incidents.task_template_urls")),
    path("tasks/", include("incidents.task_urls")),
    path("comments/", include("incidents.comment_urls")),
    path("me/", include("notifications.urls")),
    path("feedback/", include("feedback.urls")),
    path("", include(blog_router.urls)),
]
