import pytest

from security.models import Organization, OrganizationMembership
from security.signals import sync_org_memberships


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme Corp", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.mark.django_db
def test_single_customer_group_creates_one_membership(django_user_model, acme):
    user = django_user_model.objects.create_user(username="alice")

    sync_org_memberships(user, ["customer:acme"])

    assert OrganizationMembership.objects.filter(user=user, organization=acme).exists()
    assert OrganizationMembership.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_multiple_customer_groups_create_multiple_memberships(django_user_model, acme, contoso):
    user = django_user_model.objects.create_user(username="bob")

    sync_org_memberships(user, ["customer:acme", "customer:contoso"])

    assert OrganizationMembership.objects.filter(user=user).count() == 2
    assert OrganizationMembership.objects.filter(user=user, organization=acme).exists()
    assert OrganizationMembership.objects.filter(user=user, organization=contoso).exists()


@pytest.mark.django_db
def test_stale_memberships_removed_on_relogin(django_user_model, acme, contoso):
    user = django_user_model.objects.create_user(username="carol")
    OrganizationMembership.objects.create(user=user, organization=acme)
    OrganizationMembership.objects.create(user=user, organization=contoso)

    sync_org_memberships(user, ["customer:contoso"])

    assert not OrganizationMembership.objects.filter(user=user, organization=acme).exists()
    assert OrganizationMembership.objects.filter(user=user, organization=contoso).exists()
    assert OrganizationMembership.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_non_customer_groups_are_ignored(django_user_model, acme):
    user = django_user_model.objects.create_user(username="dave")

    sync_org_memberships(user, ["admins", "vpn-users", "customer:acme"])

    assert OrganizationMembership.objects.filter(user=user).count() == 1
    assert OrganizationMembership.objects.filter(user=user, organization=acme).exists()


@pytest.mark.django_db
def test_no_customer_groups_results_in_no_memberships(django_user_model):
    user = django_user_model.objects.create_user(username="eve")

    sync_org_memberships(user, ["admins", "vpn-users"])

    assert OrganizationMembership.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_unknown_org_slug_is_silently_skipped(django_user_model):
    user = django_user_model.objects.create_user(username="frank")

    sync_org_memberships(user, ["customer:ghost"])

    assert OrganizationMembership.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_user_without_pk_is_skipped(django_user_model, acme):
    user = django_user_model()  # unsaved, no pk

    sync_org_memberships(user, ["customer:acme"])

    assert OrganizationMembership.objects.count() == 0


@pytest.mark.django_db
def test_wazuh_group_defaults_to_slug_when_not_provided():
    org = Organization.objects.create(name="Test Org", slug="test-org")
    assert org.wazuh_group == "test-org"


@pytest.mark.django_db
def test_wazuh_group_preserved_when_explicitly_set():
    org = Organization.objects.create(name="Test Org", slug="test-org", wazuh_group="custom-group")
    assert org.wazuh_group == "custom-group"
