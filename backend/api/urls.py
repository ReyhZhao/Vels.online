from django.urls import include, path

from blog.urls import router as blog_router

from . import views

urlpatterns = [
    path("health/", views.HealthView.as_view()),
    path("me/", views.MeView.as_view()),
    path("logout/", views.LogoutView.as_view()),
    path("status/", include("status.urls")),
    path("security/", include("security.urls")),
    path("", include(blog_router.urls)),
]
