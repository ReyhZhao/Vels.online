from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserProfile
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

    def patch(self, request):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        default_org_slug = request.data.get("default_org_slug")
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        if default_org_slug is None:
            profile.default_org = None
        else:
            from security.models import Organization
            try:
                if request.user.is_staff:
                    org = Organization.objects.get(slug=default_org_slug)
                else:
                    org = Organization.objects.get(
                        slug=default_org_slug,
                        memberships__user=request.user,
                    )
            except Organization.DoesNotExist:
                return Response({"detail": "Organisation not found."}, status=status.HTTP_400_BAD_REQUEST)
            profile.default_org = org

        profile.save()
        return Response(UserSerializer(request.user).data)


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        django_logout(request)
        return Response({"detail": "Logged out."})
