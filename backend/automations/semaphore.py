import logging

import requests
from django.conf import settings
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class SemaphoreAPIError(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Semaphore API error {status_code}: {body}")


_STATUS_MAP = {
    "waiting": "waiting",
    "running": "running",
    "success": "success",
    "error": "error",
    # Semaphore also uses these synonyms
    "stopped": "error",
    "failed": "error",
}


class SemaphoreClient:
    def __init__(self):
        self._base_url = settings.SEMAPHORE_URL.rstrip("/")
        self._token = settings.SEMAPHORE_API_TOKEN
        self._project_id = settings.SEMAPHORE_PROJECT_ID

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _check(self, response):
        if not response.ok:
            logger.error(
                "Semaphore API error: %s %s → %s\nResponse body: %s",
                response.request.method if response.request else "?",
                response.url,
                response.status_code,
                response.text or "(empty)",
            )
            raise SemaphoreAPIError(response.status_code, response.text)
        return response

    def _get(self, path, **kwargs):
        url = f"{self._base_url}/api{path}"
        logger.debug("Semaphore GET %s", url)
        try:
            return requests.get(url, headers=self._headers(), timeout=10, **kwargs)
        except RequestException as exc:
            logger.error("Semaphore GET %s failed: %s", url, exc)
            raise SemaphoreAPIError(0, str(exc)) from exc

    def _post(self, path, **kwargs):
        url = f"{self._base_url}/api{path}"
        logger.debug("Semaphore POST %s payload=%s", url, kwargs.get("json"))
        try:
            return requests.post(url, headers=self._headers(), timeout=10, **kwargs)
        except RequestException as exc:
            logger.error("Semaphore POST %s failed: %s", url, exc)
            raise SemaphoreAPIError(0, str(exc)) from exc

    def list_templates(self):
        """Return [{id, name}] for all templates in the configured project."""
        resp = self._get(f"/project/{self._project_id}/templates")
        self._check(resp)
        return [{"id": t["id"], "name": t.get("name") or t.get("alias", "")} for t in resp.json()]

    def launch_job(self, template_id, extra_vars=None):
        """Launch a Semaphore task and return the task ID integer."""
        payload = {"template_id": template_id}
        if extra_vars:
            payload["environment"] = {"ENV": extra_vars}
        resp = self._post(f"/project/{self._project_id}/tasks", json=payload)
        self._check(resp)
        return resp.json()["id"]

    def get_job_status(self, semaphore_task_id):
        """Return one of: waiting | running | success | error."""
        resp = self._get(f"/project/{self._project_id}/tasks/{semaphore_task_id}")
        self._check(resp)
        raw = resp.json().get("status", "")
        return _STATUS_MAP.get(raw, "error")
