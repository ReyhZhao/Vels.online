from django.urls import include, path

from . import views
from blog.urls import router as blog_router

urlpatterns = [
    path("health/", views.health),
    path("me/", views.me),
    path("status/", include("status.urls")),
    path("security/", include("security.urls")),
    path("", include(blog_router.urls)),
]
