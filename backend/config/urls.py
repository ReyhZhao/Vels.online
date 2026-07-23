from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token

from webhook_ingest.views import IngestReceiverView


def login_redirect_view(request):
    if request.user.is_authenticated:
        return redirect("/dashboard")
    return redirect("/")


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/auth-token/", obtain_auth_token, name="api-token-auth"),
    path("api/", include("api.urls")),
    path("ingest/<uuid:path_uuid>/", IngestReceiverView.as_view(), name="webhook-ingest-receiver"),
    path("auth/", include("allauth.urls")),
    path("login-redirect/", login_redirect_view),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/schema/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
