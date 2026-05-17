from allauth.socialaccount.signals import social_account_added, social_account_updated
from django.dispatch import receiver

from security.models import Organization, OrganizationMembership

_CUSTOMER_PREFIX = "customer:"


def _complete_signup_request(org_slug):
    try:
        from signups.models import SignupRequest

        for req in SignupRequest.objects.filter(
            org_slug=org_slug, status=SignupRequest.STATUS_APPROVED
        ):
            req.complete()
            req.save(update_fields=["status"])
    except Exception:
        pass


def _apply_org_invitation_grants(user, org):
    """Apply role grants from any pending OrgInvitation for this user+org."""
    try:
        from security.models import OrgInvitation

        inv = OrgInvitation.objects.filter(
            organization=org,
            email__iexact=user.email,
            status=OrgInvitation.STATUS_PENDING,
        ).first()
        if not inv:
            return

        update_fields = []
        if inv.role in (OrgInvitation.ROLE_STAFF, OrgInvitation.ROLE_ADMIN) and not user.is_staff:
            user.is_staff = True
            update_fields.append("is_staff")
        if inv.role == OrgInvitation.ROLE_ADMIN and not user.is_superuser:
            user.is_superuser = True
            update_fields.append("is_superuser")
        if update_fields:
            user.save(update_fields=update_fields)

        inv.status = OrgInvitation.STATUS_ACCEPTED
        inv.save(update_fields=["status"])
    except Exception:
        pass


def sync_org_memberships(user, groups):
    """Sync a user's OrganizationMembership records from their OIDC group claims."""
    if not user.pk:
        return

    org_slugs = {
        g[len(_CUSTOMER_PREFIX):]
        for g in groups
        if isinstance(g, str) and g.startswith(_CUSTOMER_PREFIX)
    }

    target_orgs = list(Organization.objects.filter(slug__in=org_slugs))

    for org in target_orgs:
        _, created = OrganizationMembership.objects.get_or_create(user=user, organization=org)
        if created:
            _complete_signup_request(org.slug)
            _apply_org_invitation_grants(user, org)

    OrganizationMembership.objects.filter(user=user).exclude(organization__in=target_orgs).delete()


@receiver(social_account_added)
def on_social_account_added(sender, request, sociallogin, **kwargs):
    sync_org_memberships(
        sociallogin.user,
        sociallogin.account.extra_data.get("groups", []),
    )


@receiver(social_account_updated)
def on_social_account_updated(sender, request, sociallogin, **kwargs):
    sync_org_memberships(
        sociallogin.user,
        sociallogin.account.extra_data.get("groups", []),
    )
