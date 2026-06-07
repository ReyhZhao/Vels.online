from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from security.models import OrganizationMembership

from .models import AssetOwner, Contact
from .serializers import ContactCreateSerializer, ContactPatchSerializer, ContactSerializer


def _get_user_org_ids(user):
    if user.is_staff:
        return None  # staff sees all
    return list(
        OrganizationMembership.objects.filter(user=user).values_list("organization_id", flat=True)
    )


def _get_contact_for_user(user, pk):
    try:
        contact = Contact.objects.select_related("organisation").get(pk=pk)
    except Contact.DoesNotExist:
        return None, Response(status=status.HTTP_404_NOT_FOUND)
    if not user.is_staff:
        if not OrganizationMembership.objects.filter(
            user=user, organization=contact.organisation
        ).exists():
            return None, Response(status=status.HTTP_404_NOT_FOUND)
    return contact, None


class ContactListView(APIView):
    def get(self, request):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        org_ids = _get_user_org_ids(request.user)
        qs = Contact.objects.select_related("organisation").order_by("name")
        if org_ids is not None:
            qs = qs.filter(organisation_id__in=org_ids)
        org_slug = request.query_params.get("org")
        if org_slug:
            qs = qs.filter(organisation__slug=org_slug)
        return Response(ContactSerializer(qs, many=True).data)

    def post(self, request):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        ser = ContactCreateSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        org = ser.validated_data["organisation"]
        if not request.user.is_staff:
            if not OrganizationMembership.objects.filter(
                user=request.user, organization=org
            ).exists():
                return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            contact = ser.save()
        except IntegrityError:
            return Response(
                {"email": "A contact with this email already exists in this organisation."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ContactSerializer(contact).data, status=status.HTTP_201_CREATED)


class ContactDetailView(APIView):
    def get(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        contact, err = _get_contact_for_user(request.user, pk)
        if err:
            return err
        return Response(ContactSerializer(contact).data)

    def patch(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        contact, err = _get_contact_for_user(request.user, pk)
        if err:
            return err
        ser = ContactPatchSerializer(contact, data=request.data, partial=True)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            contact = ser.save()
        except IntegrityError:
            return Response(
                {"email": "A contact with this email already exists in this organisation."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(ContactSerializer(contact).data)

    def delete(self, request, pk):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        contact, err = _get_contact_for_user(request.user, pk)
        if err:
            return err
        contact.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ContactAssetListView(APIView):
    def _get_contact(self, request, contact_pk):
        if not request.user.is_authenticated:
            return None, Response(status=status.HTTP_401_UNAUTHORIZED)
        return _get_contact_for_user(request.user, contact_pk)

    def get(self, request, contact_pk):
        contact, err = self._get_contact(request, contact_pk)
        if err:
            return err
        from incidents.models import Asset
        from incidents.serializers import AssetSerializer
        assets = Asset.objects.filter(asset_ownerships__contact=contact).select_related("organization", "route")
        return Response(AssetSerializer(assets, many=True).data)

    def post(self, request, contact_pk):
        contact, err = self._get_contact(request, contact_pk)
        if err:
            return err
        from incidents.models import Asset
        from incidents.serializers import AssetSerializer
        asset_id = request.data.get("asset_id")
        if not asset_id:
            return Response({"detail": "asset_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            asset = Asset.objects.get(pk=asset_id)
        except Asset.DoesNotExist:
            return Response({"detail": "Asset not found."}, status=status.HTTP_400_BAD_REQUEST)
        if asset.organization_id != contact.organisation_id:
            return Response({"detail": "Asset belongs to a different organisation."}, status=status.HTTP_400_BAD_REQUEST)
        AssetOwner.objects.get_or_create(contact=contact, asset=asset)
        assets = Asset.objects.filter(asset_ownerships__contact=contact).select_related("organization", "route")
        return Response(AssetSerializer(assets, many=True).data, status=status.HTTP_201_CREATED)


class ContactAssetDetailView(APIView):
    def delete(self, request, contact_pk, asset_pk):
        if not request.user.is_authenticated:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        contact, err = _get_contact_for_user(request.user, contact_pk)
        if err:
            return err
        deleted, _ = AssetOwner.objects.filter(contact=contact, asset_id=asset_pk).delete()
        if not deleted:
            return Response(status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
