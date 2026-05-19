from unittest.mock import MagicMock, patch

import pytest

from automations.models import Automation
from automations.semaphore import SemaphoreAPIError
from incidents.models import Incident, Task
from incidents.tasks import poll_automated_tasks
from notifications.models import Notification
from security.models import Organization


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


@pytest.fixture
def automation(db, django_user_model):
    staff = django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)
    return Automation.objects.create(
        name="Malware Scan",
        semaphore_template_id=42,
        created_by=staff,
    )


@pytest.fixture
def assignee(db, django_user_model):
    return django_user_model.objects.create_user(
        username="assignee", password="pass", is_staff=True
    )


@pytest.fixture
def incident(acme, assignee):
    return Incident.objects.create(
        organization=acme,
        title="Test Incident",
        display_id="INC-2026-0001",
        assignee=assignee,
    )


@pytest.fixture
def automated_task(incident, automation):
    return Task.objects.create(
        incident=incident,
        title="Run scan",
        task_type=Task.TYPE_AUTOMATED,
        automation=automation,
        semaphore_task_id=99,
        state=Task.STATE_IN_PROGRESS,
    )


@pytest.fixture
def semaphore_settings(settings):
    settings.SEMAPHORE_URL = "https://semaphore.example.com"
    settings.SEMAPHORE_API_TOKEN = "test-token"
    settings.SEMAPHORE_PROJECT_ID = 1


class TestPollAutomatedTasks:
    def test_success_sets_done_and_closed_at(self, automated_task, semaphore_settings):
        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            MockClient.return_value.get_job_status.return_value = "success"
            result = poll_automated_tasks()

        automated_task.refresh_from_db()
        assert automated_task.state == Task.STATE_DONE
        assert automated_task.closed_at is not None
        assert automated_task.automation_error is None
        assert result["done"] == 1

    def test_error_sets_new_and_error_message(self, automated_task, semaphore_settings):
        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            MockClient.return_value.get_job_status.return_value = "error"
            poll_automated_tasks()

        automated_task.refresh_from_db()
        assert automated_task.state == Task.STATE_NEW
        assert automated_task.semaphore_task_id is None
        assert automated_task.automation_error is not None

    def test_failed_status_also_sets_new(self, automated_task, semaphore_settings):
        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            MockClient.return_value.get_job_status.return_value = "failed"
            poll_automated_tasks()

        automated_task.refresh_from_db()
        assert automated_task.state == Task.STATE_NEW

    def test_waiting_status_is_noop(self, automated_task, semaphore_settings):
        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            MockClient.return_value.get_job_status.return_value = "waiting"
            poll_automated_tasks()

        automated_task.refresh_from_db()
        assert automated_task.state == Task.STATE_IN_PROGRESS
        assert automated_task.semaphore_task_id == 99

    def test_running_status_is_noop(self, automated_task, semaphore_settings):
        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            MockClient.return_value.get_job_status.return_value = "running"
            poll_automated_tasks()

        automated_task.refresh_from_db()
        assert automated_task.state == Task.STATE_IN_PROGRESS

    def test_exception_for_one_task_does_not_abort_rest(self, automated_task, incident, automation, semaphore_settings):
        second = Task.objects.create(
            incident=incident,
            title="Second scan",
            task_type=Task.TYPE_AUTOMATED,
            automation=automation,
            semaphore_task_id=100,
            state=Task.STATE_IN_PROGRESS,
        )

        def side_effect(semaphore_task_id):
            if semaphore_task_id == 99:
                raise SemaphoreAPIError(500, "boom")
            return "success"

        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            MockClient.return_value.get_job_status.side_effect = side_effect
            result = poll_automated_tasks()

        automated_task.refresh_from_db()
        second.refresh_from_db()
        assert automated_task.state == Task.STATE_IN_PROGRESS
        assert second.state == Task.STATE_DONE
        assert result["processed"] == 2
        assert result["done"] == 1

    def test_done_task_is_skipped(self, incident, automation, semaphore_settings):
        done_task = Task.objects.create(
            incident=incident,
            title="Already done",
            task_type=Task.TYPE_AUTOMATED,
            automation=automation,
            semaphore_task_id=77,
            state=Task.STATE_DONE,
        )

        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            result = poll_automated_tasks()

        MockClient.return_value.get_job_status.assert_not_called()
        assert result["processed"] == 0

    def test_manual_task_is_skipped(self, incident, semaphore_settings):
        Task.objects.create(
            incident=incident,
            title="Manual",
            task_type=Task.TYPE_MANUAL,
            semaphore_task_id=55,
            state=Task.STATE_IN_PROGRESS,
        )

        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            result = poll_automated_tasks()

        MockClient.return_value.get_job_status.assert_not_called()
        assert result["processed"] == 0

    def test_success_creates_task_complete_notification(self, automated_task, assignee, semaphore_settings):
        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            MockClient.return_value.get_job_status.return_value = "success"
            poll_automated_tasks()

        notif = Notification.objects.filter(
            recipient=assignee,
            kind=Notification.KIND_TASK_COMPLETE,
            task=automated_task,
        ).first()
        assert notif is not None
        assert automated_task.incident.display_id in notif.payload["body"]

    def test_failure_does_not_create_notification(self, automated_task, assignee, semaphore_settings):
        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            MockClient.return_value.get_job_status.return_value = "error"
            poll_automated_tasks()

        assert not Notification.objects.filter(
            recipient=assignee,
            kind=Notification.KIND_TASK_COMPLETE,
        ).exists()

    def test_no_notification_when_incident_has_no_assignee(self, incident, automation, semaphore_settings, django_user_model):
        incident.assignee = None
        incident.save()
        task = Task.objects.create(
            incident=incident,
            title="Unassigned scan",
            task_type=Task.TYPE_AUTOMATED,
            automation=automation,
            semaphore_task_id=88,
            state=Task.STATE_IN_PROGRESS,
        )

        with patch("automations.semaphore.SemaphoreClient") as MockClient:
            MockClient.return_value.get_job_status.return_value = "success"
            poll_automated_tasks()

        assert not Notification.objects.filter(kind=Notification.KIND_TASK_COMPLETE).exists()
