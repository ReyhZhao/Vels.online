import requests
from django.conf import settings
from requests.exceptions import RequestException


class BunkerWebError(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        super().__init__(f"BunkerWeb API error {status_code}: {body}")


class BunkerWebClient:
    def __init__(self):
        self._base_url = settings.BUNKERWEB_API_URL.rstrip("/")
        self._token = settings.BUNKERWEB_API_TOKEN

    def _headers(self):
        return {"Authorization": f"Bearer {self._token}"}

    def _check(self, response):
        if not response.ok:
            raise BunkerWebError(response.status_code, response.text)
        return response

    def _get(self, path, **kwargs):
        try:
            return requests.get(f"{self._base_url}{path}", headers=self._headers(), timeout=10, **kwargs)
        except RequestException as exc:
            raise BunkerWebError(0, str(exc)) from exc

    def _post(self, path, **kwargs):
        try:
            return requests.post(f"{self._base_url}{path}", headers=self._headers(), timeout=10, **kwargs)
        except RequestException as exc:
            raise BunkerWebError(0, str(exc)) from exc

    def _patch(self, path, **kwargs):
        try:
            return requests.patch(f"{self._base_url}{path}", headers=self._headers(), timeout=10, **kwargs)
        except RequestException as exc:
            raise BunkerWebError(0, str(exc)) from exc

    def _delete(self, path, **kwargs):
        try:
            return requests.delete(f"{self._base_url}{path}", headers=self._headers(), timeout=10, **kwargs)
        except RequestException as exc:
            raise BunkerWebError(0, str(exc)) from exc

    def create_service(self, fqdn, backend_host, backend_port, backend_protocol):
        resp = self._post("/services", json={
            "server_name": fqdn,
            "backend_host": backend_host,
            "backend_port": backend_port,
            "backend_protocol": backend_protocol,
        })
        self._check(resp)
        return resp.json()

    def delete_service(self, fqdn):
        resp = self._delete(f"/services/{fqdn}")
        self._check(resp)

    def get_service_settings(self, fqdn):
        resp = self._get(f"/services/{fqdn}", params={"full": "true"})
        self._check(resp)
        return resp.json()

    def update_service_settings(self, fqdn, settings: dict):
        resp = self._patch(f"/services/{fqdn}", json=settings)
        self._check(resp)
        return resp.json()

    def get_service_reports(self, fqdn):
        resp = self._get(f"/services/{fqdn}/reports")
        self._check(resp)
        return resp.json()

    def list_services(self):
        resp = self._get("/services")
        self._check(resp)
        return resp.json()
