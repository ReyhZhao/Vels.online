from unittest.mock import MagicMock, patch

import pytest

from automations.models import Automation
from automations.semaphore import SemaphoreAPIError, SemaphoreClient


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def semaphore_settings(settings):
    settings.SEMAPHORE_URL = "https://semaphore.example.com"
    settings.SEMAPHORE_API_TOKEN = "test-token"
    settings.SEMAPHORE_PROJECT_ID = 1


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


@pytest.fixture
def regular_user(db, django_user_model):
    return django_user_model.objects.create_user(username="user", password="pass")


@pytest.fixture
def automation(db, staff):
    return Automation.objects.create(
        name="Malware Scan",
        semaphore_template_id=42,
        semaphore_template_name="malware-scan",
        created_by=staff,
    )


# ── SemaphoreClient unit tests ────────────────────────────────────────────────


class TestSemaphoreClientListTemplates:
    def test_returns_id_and_name_from_name_field(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [
            {"id": 1, "name": "deploy-prod"},
            {"id": 2, "name": "malware-scan"},
        ]
        with patch("automations.semaphore.requests.get", return_value=mock_resp) as mock_get:
            result = SemaphoreClient().list_templates()

        assert result == [{"id": 1, "name": "deploy-prod"}, {"id": 2, "name": "malware-scan"}]
        mock_get.assert_called_once()
        url = mock_get.call_args[0][0]
        assert "/project/1/templates" in url

    def test_falls_back_to_alias_when_name_absent(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [{"id": 3, "alias": "legacy-job"}]
        with patch("automations.semaphore.requests.get", return_value=mock_resp):
            result = SemaphoreClient().list_templates()
        assert result == [{"id": 3, "name": "legacy-job"}]

    def test_prefers_name_over_alias_when_both_present(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [{"id": 4, "name": "current-name", "alias": "old-alias"}]
        with patch("automations.semaphore.requests.get", return_value=mock_resp):
            result = SemaphoreClient().list_templates()
        assert result == [{"id": 4, "name": "current-name"}]

    def test_returns_empty_string_when_neither_name_nor_alias_present(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = [{"id": 5}]
        with patch("automations.semaphore.requests.get", return_value=mock_resp):
            result = SemaphoreClient().list_templates()
        assert result == [{"id": 5, "name": ""}]

    def test_raises_on_non_2xx(self):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        with patch("automations.semaphore.requests.get", return_value=mock_resp):
            with pytest.raises(SemaphoreAPIError) as exc_info:
                SemaphoreClient().list_templates()
        assert "500" in str(exc_info.value)

    def test_raises_on_network_error(self):
        from requests.exceptions import ConnectionError

        with patch("automations.semaphore.requests.get", side_effect=ConnectionError("refused")):
            with pytest.raises(SemaphoreAPIError):
                SemaphoreClient().list_templates()


class TestSemaphoreClientLaunchJob:
    def test_returns_task_id(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"id": 99}
        with patch("automations.semaphore.requests.post", return_value=mock_resp) as mock_post:
            task_id = SemaphoreClient().launch_job(template_id=42, extra_vars={"host": "10.0.0.1"})

        assert task_id == 99
        payload = mock_post.call_args[1]["json"]
        assert payload["template_id"] == 42

    def test_raises_on_non_2xx(self):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        with patch("automations.semaphore.requests.post", return_value=mock_resp):
            with pytest.raises(SemaphoreAPIError):
                SemaphoreClient().launch_job(42)

    def test_raises_on_network_error(self):
        from requests.exceptions import Timeout

        with patch("automations.semaphore.requests.post", side_effect=Timeout()):
            with pytest.raises(SemaphoreAPIError):
                SemaphoreClient().launch_job(42)


class TestSemaphoreClientGetJobStatus:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("waiting", "waiting"),
            ("running", "running"),
            ("success", "success"),
            ("error", "error"),
            ("failed", "error"),
            ("stopped", "error"),
            ("unknown_value", "error"),
        ],
    )
    def test_status_mapping(self, raw, expected):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"status": raw}
        with patch("automations.semaphore.requests.get", return_value=mock_resp):
            result = SemaphoreClient().get_job_status(99)
        assert result == expected

    def test_calls_correct_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.ok = True
        mock_resp.json.return_value = {"status": "success"}
        with patch("automations.semaphore.requests.get", return_value=mock_resp) as mock_get:
            SemaphoreClient().get_job_status(77)
        url = mock_get.call_args[0][0]
        assert "/project/1/tasks/77" in url

    def test_raises_on_non_2xx(self):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 404
        mock_resp.text = "Not found"
        with patch("automations.semaphore.requests.get", return_value=mock_resp):
            with pytest.raises(SemaphoreAPIError):
                SemaphoreClient().get_job_status(999)


# ── GET /api/automations/ ─────────────────────────────────────────────────────


@pytest.mark.django_db
def test_list_automations_requires_staff(client, regular_user):
    client.force_login(regular_user)
    resp = client.get("/api/automations/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_list_automations_empty(client, staff):
    client.force_login(staff)
    resp = client.get("/api/automations/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.django_db
def test_list_automations_returns_active(client, staff, automation):
    client.force_login(staff)
    resp = client.get("/api/automations/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Malware Scan"
    assert data[0]["semaphore_template_id"] == 42


@pytest.mark.django_db
def test_list_automations_excludes_archived(client, staff, automation):
    automation.archived = True
    automation.save()
    client.force_login(staff)
    resp = client.get("/api/automations/")
    assert resp.status_code == 200
    assert resp.json() == []


# ── POST /api/automations/ ────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_automation_requires_staff(client, regular_user):
    client.force_login(regular_user)
    resp = client.post(
        "/api/automations/",
        {"name": "Test", "semaphore_template_id": 1},
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_create_automation_success(client, staff):
    client.force_login(staff)
    resp = client.post(
        "/api/automations/",
        {"name": "Deploy Patch", "semaphore_template_id": 5, "semaphore_template_name": "deploy-patch"},
        content_type="application/json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Deploy Patch"
    assert data["semaphore_template_id"] == 5
    assert Automation.objects.filter(name="Deploy Patch").exists()


@pytest.mark.django_db
def test_create_automation_validates_required_fields(client, staff):
    client.force_login(staff)
    resp = client.post(
        "/api/automations/",
        {"semaphore_template_id": 5},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "name" in resp.json()["detail"]


@pytest.mark.django_db
def test_create_automation_validates_template_id(client, staff):
    client.force_login(staff)
    resp = client.post(
        "/api/automations/",
        {"name": "Test"},
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "semaphore_template_id" in resp.json()["detail"]


# ── PATCH /api/automations/<id>/ ──────────────────────────────────────────────


@pytest.mark.django_db
def test_patch_automation_requires_staff(client, regular_user, automation):
    client.force_login(regular_user)
    resp = client.patch(
        f"/api/automations/{automation.pk}/",
        {"name": "Updated"},
        content_type="application/json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_patch_automation_updates_name(client, staff, automation):
    client.force_login(staff)
    resp = client.patch(
        f"/api/automations/{automation.pk}/",
        {"name": "Renamed Scan"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed Scan"
    automation.refresh_from_db()
    assert automation.name == "Renamed Scan"


@pytest.mark.django_db
def test_patch_automation_404_for_missing(client, staff):
    client.force_login(staff)
    resp = client.patch(
        "/api/automations/9999/",
        {"name": "X"},
        content_type="application/json",
    )
    assert resp.status_code == 404


# ── DELETE /api/automations/<id>/ ────────────────────────────────────────────


@pytest.mark.django_db
def test_delete_automation_requires_staff(client, regular_user, automation):
    client.force_login(regular_user)
    resp = client.delete(f"/api/automations/{automation.pk}/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_delete_automation_archives_instead_of_deleting(client, staff, automation):
    client.force_login(staff)
    resp = client.delete(f"/api/automations/{automation.pk}/")
    assert resp.status_code == 204
    automation.refresh_from_db()
    assert automation.archived is True
    assert Automation.objects.filter(pk=automation.pk).exists()


# ── GET /api/semaphore/templates/ ─────────────────────────────────────────────


@pytest.mark.django_db
def test_semaphore_templates_requires_staff(client, regular_user):
    client.force_login(regular_user)
    resp = client.get("/api/semaphore/templates/")
    assert resp.status_code == 403


@pytest.mark.django_db
def test_semaphore_templates_proxies_response(client, staff):
    mock_client = MagicMock()
    mock_client.list_templates.return_value = [{"id": 1, "name": "deploy-prod"}]
    with patch("automations.views.SemaphoreClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.get("/api/semaphore/templates/")
    assert resp.status_code == 200
    assert resp.json() == [{"id": 1, "name": "deploy-prod"}]


@pytest.mark.django_db
def test_semaphore_templates_returns_502_on_error(client, staff):
    mock_client = MagicMock()
    mock_client.list_templates.side_effect = SemaphoreAPIError(500, "boom")
    with patch("automations.views.SemaphoreClient", return_value=mock_client):
        client.force_login(staff)
        resp = client.get("/api/semaphore/templates/")
    assert resp.status_code == 502
