from rest_framework.response import Response
from rest_framework.views import APIView

from .models import StaffProfile
from .serializers import StaffProfileSerializer


class StaffProfileView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        profile, _ = StaffProfile.objects.get_or_create(user=request.user)
        return Response(StaffProfileSerializer(profile).data)

    def patch(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        profile, _ = StaffProfile.objects.get_or_create(user=request.user)
        serializer = StaffProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
