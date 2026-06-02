from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ShiftBlock, StaffProfile, validate_tiling
from .serializers import ShiftBlockSerializer, StaffProfileSerializer


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


class ShiftBlockListView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        blocks = ShiftBlock.objects.all().order_by("order")
        return Response(ShiftBlockSerializer(blocks, many=True).data)

    def post(self, request):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        if not request.user.is_superuser:
            return Response(status=403)
        serializer = ShiftBlockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                block = serializer.save()
                validate_tiling()
        except DjangoValidationError as exc:
            return Response({"detail": exc.message}, status=400)
        return Response(ShiftBlockSerializer(block).data, status=201)


class ShiftBlockDetailView(APIView):
    def _get_block(self, pk):
        try:
            return ShiftBlock.objects.get(pk=pk), None
        except ShiftBlock.DoesNotExist:
            return None, Response(status=404)

    def patch(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        if not request.user.is_superuser:
            return Response(status=403)
        block, err = self._get_block(pk)
        if err:
            return err
        serializer = ShiftBlockSerializer(block, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                block = serializer.save()
                validate_tiling()
        except DjangoValidationError as exc:
            return Response({"detail": exc.message}, status=400)
        return Response(ShiftBlockSerializer(block).data)

    def delete(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=401)
        if not request.user.is_staff:
            return Response(status=403)
        if not request.user.is_superuser:
            return Response(status=403)
        block, err = self._get_block(pk)
        if err:
            return err
        try:
            with transaction.atomic():
                block.delete()
                validate_tiling(exclude_pk=pk)
        except DjangoValidationError as exc:
            return Response({"detail": exc.message}, status=400)
        return Response(status=204)
