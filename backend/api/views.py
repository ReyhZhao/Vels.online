from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserSerializer


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class MeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        # Ensure csrftoken cookie is written so mutating API calls (POST/PATCH)
        # can include it via X-CSRFToken. API views are @csrf_exempt at the
        # Django middleware level, so without this the cookie is never set.
        # We also return the token in the X-CSRFToken response header so the
        # SPA can set it as a permanent axios default rather than relying on
        # reading document.cookie, which may fail in strict browser contexts.
        csrf_token = get_token(request._request)
        if not request.user.is_authenticated:
            resp = Response(status=status.HTTP_401_UNAUTHORIZED)
            resp['X-CSRFToken'] = csrf_token
            return resp
        resp = Response(UserSerializer(request.user).data)
        resp['X-CSRFToken'] = csrf_token
        return resp


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        django_logout(request)
        return Response({"detail": "Logged out."})
