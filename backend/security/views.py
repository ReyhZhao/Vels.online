from django.db import transaction
from django.utils.text import slugify
from rest_framework.decorators import api_view
from rest_framework.response import Response

from security.models import Organization, OrganizationMembership
from security.wazuh import WazuhAPIError, WazuhAuthError, WazuhClient


def _generate_slug(name):
    base = slugify(name)
    slug = base
    n = 2
    while Organization.objects.filter(slug=slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _serialize_org(org):
    return {
        "id": org.id,
        "name": org.name,
        "slug": org.slug,
        "wazuh_group": org.wazuh_group,
    }


@api_view(["GET", "POST"])
def organizations_view(request):
    if request.method == "GET":
        if request.user.is_staff:
            orgs = Organization.objects.all().order_by("name")
        else:
            orgs = Organization.objects.filter(
                memberships__user=request.user
            ).order_by("name")
        return Response([_serialize_org(o) for o in orgs])

    # POST — admin only
    if not request.user.is_staff:
        return Response(status=403)

    name = request.data.get("name", "").strip()
    if not name:
        return Response({"detail": "name is required."}, status=400)

    slug = _generate_slug(name)

    try:
        with transaction.atomic():
            org = Organization.objects.create(name=name, slug=slug)
            WazuhClient().create_group(org.wazuh_group)
    except (WazuhAPIError, WazuhAuthError) as exc:
        return Response({"detail": f"Failed to create Wazuh group: {exc}"}, status=400)

    return Response(_serialize_org(org), status=201)
