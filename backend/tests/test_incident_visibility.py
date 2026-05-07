import pytest
from security.models import Organization, OrganizationMembership
from incidents.models import Incident
from incidents.services.visibility import can_view_incident, filter_incidents_for_user


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def contoso(db):
    return Organization.objects.create(name="Contoso", slug="contoso", wazuh_group="contoso")


@pytest.fixture
def alice(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def acme_member(alice, acme):
    OrganizationMembership.objects.create(user=alice, organization=acme)
    return alice


def make_incident(org, tlp="amber"):
    return Incident.objects.create(organization=org, title="Test", tlp=tlp, display_id=f"INC-2026-{org.slug}-{tlp}")


# ── can_view_incident ───────────────────────────────────────────────────────


@pytest.mark.django_db
def test_staff_can_view_any_tlp(staff, acme):
    incident = make_incident(acme, tlp="red")
    assert can_view_incident(staff, incident) is True


@pytest.mark.django_db
def test_staff_can_view_other_org(staff, contoso):
    incident = make_incident(contoso, tlp="amber")
    assert can_view_incident(staff, incident) is True


@pytest.mark.django_db
def test_member_can_view_own_org_amber(acme_member, acme):
    incident = make_incident(acme, tlp="amber")
    assert can_view_incident(acme_member, incident) is True


@pytest.mark.django_db
def test_member_cannot_view_tlp_red(acme_member, acme):
    incident = make_incident(acme, tlp="red")
    assert can_view_incident(acme_member, incident) is False


@pytest.mark.django_db
def test_member_cannot_view_other_org(acme_member, contoso):
    incident = make_incident(contoso, tlp="amber")
    assert can_view_incident(acme_member, incident) is False


@pytest.mark.django_db
def test_non_member_cannot_view(alice, acme):
    incident = make_incident(acme, tlp="green")
    assert can_view_incident(alice, incident) is False


# ── filter_incidents_for_user ───────────────────────────────────────────────


@pytest.mark.django_db
def test_filter_staff_sees_all(staff, acme, contoso):
    i1 = make_incident(acme, tlp="red")
    i2 = make_incident(contoso, tlp="amber")
    qs = filter_incidents_for_user(Incident.objects.all(), staff)
    ids = list(qs.values_list("id", flat=True))
    assert i1.id in ids
    assert i2.id in ids


@pytest.mark.django_db
def test_filter_member_sees_own_non_red(acme_member, acme, contoso):
    visible = make_incident(acme, tlp="amber")
    hidden_red = make_incident(acme, tlp="red")
    hidden_other = make_incident(contoso, tlp="green")
    qs = filter_incidents_for_user(Incident.objects.all(), acme_member)
    ids = list(qs.values_list("id", flat=True))
    assert visible.id in ids
    assert hidden_red.id not in ids
    assert hidden_other.id not in ids


@pytest.mark.django_db
def test_filter_non_member_sees_nothing(alice, acme):
    make_incident(acme, tlp="green")
    qs = filter_incidents_for_user(Incident.objects.all(), alice)
    assert qs.count() == 0
