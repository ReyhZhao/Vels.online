"""Subject-linked Classification Correction troubleshooting surface (ADR-0030).

Corrections are captured by ``capture_classification_correction`` but had no UI. These tests
cover the staff-only ``/api/subjects/<pk>/corrections/`` endpoint and the ``correction_count``
badge on the subjects list — the read surface for troubleshooting Classify accuracy per
subject. Corrections carry cross-org incident references, so the surface is staff-only.
"""
import pytest
from rest_framework.test import APIClient

from incidents.memory.corrections import capture_classification_correction
from incidents.models import Comment, Incident, Subject
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def brute(db):
    subj, _ = Subject.objects.get_or_create(slug="brute-force", defaults={"name": "Brute Force"})
    return subj


@pytest.fixture
def malware(db):
    subj, _ = Subject.objects.get_or_create(slug="malware", defaults={"name": "Malware"})
    return subj


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="s", password="p", is_staff=True)


def _make_correction(acme, staff, *, final_subject, agent_slug):
    """Triage an incident (agent baseline) then have a human overturn it to ``final_subject``."""
    n = Incident.objects.count()
    inc = Incident.objects.create(organization=acme, title=f"alert {n}",
                                  display_id=f"INC-2026-{n + 1:04d}",
                                  subject=final_subject, severity="medium", state="triaged")
    Comment.objects.create(
        incident=inc, kind=Comment.KIND_AI_TRIAGE, body="classify", is_internal=True,
        metadata={"subject_recommendation": agent_slug, "severity_recommendation": "medium"},
    )
    return capture_classification_correction(inc, actor=staff, new_subject=final_subject)


@pytest.mark.django_db
def test_endpoint_returns_corrections_touching_the_subject(acme, brute, malware, staff):
    # Agent said brute-force, human corrected to malware → touches BOTH subjects.
    corr = _make_correction(acme, staff, final_subject=malware, agent_slug="brute-force")
    assert corr is not None

    client = APIClient()
    client.force_authenticate(staff)

    # Appears under the subject the human moved TO (the missed subject)...
    resp = client.get(f"/api/subjects/{malware.id}/corrections/")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    row = resp.data[0]
    assert row["agent_subject_name"] == "Brute Force"
    assert row["human_subject_name"] == "Malware"
    assert row["incident_display_id"] == corr.incident.display_id
    assert row["organization_slug"] == "acme"
    assert row["actor_username"] == "s"

    # ...and under the subject the agent wrongly applied (over-applied subject).
    resp = client.get(f"/api/subjects/{brute.id}/corrections/")
    assert len(resp.data) == 1
    assert resp.data[0]["human_subject_name"] == "Malware"


@pytest.mark.django_db
def test_endpoint_is_staff_only(acme, brute, malware, staff, django_user_model):
    _make_correction(acme, staff, final_subject=malware, agent_slug="brute-force")
    client = APIClient()

    tenant = django_user_model.objects.create_user(username="t", password="p")
    client.force_authenticate(tenant)
    assert client.get(f"/api/subjects/{malware.id}/corrections/").status_code == 403

    client.force_authenticate(staff)
    assert client.get(f"/api/subjects/{malware.id}/corrections/").status_code == 200


@pytest.mark.django_db
def test_unrelated_subject_has_no_corrections(acme, brute, malware, staff):
    _make_correction(acme, staff, final_subject=malware, agent_slug="brute-force")
    other, _ = Subject.objects.get_or_create(slug="phishing", defaults={"name": "Phishing"})

    client = APIClient()
    client.force_authenticate(staff)
    resp = client.get(f"/api/subjects/{other.id}/corrections/")
    assert resp.status_code == 200
    assert resp.data == []


@pytest.mark.django_db
def test_correction_count_on_list_is_staff_only(acme, brute, malware, staff, django_user_model):
    _make_correction(acme, staff, final_subject=malware, agent_slug="brute-force")

    client = APIClient()

    # Staff sees the count (both touched subjects show 1).
    client.force_authenticate(staff)
    rows = {s["slug"]: s for s in client.get("/api/subjects/").data}
    assert rows["malware"]["correction_count"] == 1
    assert rows["brute-force"]["correction_count"] == 1

    # A tenant never sees cross-org correction volume — the field stays null.
    tenant = django_user_model.objects.create_user(username="t2", password="p")
    client.force_authenticate(tenant)
    rows = {s["slug"]: s for s in client.get("/api/subjects/").data}
    assert rows["malware"]["correction_count"] is None
