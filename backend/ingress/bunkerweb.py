import requests
from django.conf import settings


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

    def create_service(self, fqdn, backend_host, backend_port, backend_protocol):
        resp = requests.post(
            f"{self._base_url}/api/v1/services",
            headers=self._headers(),
            json={
                "server_name": fqdn,
                "backend_host": backend_host,
                "backend_port": backend_port,
                "backend_protocol": backend_protocol,
            },
            timeout=10,
        )
        self._check(resp)
        return resp.json()

    def delete_service(self, fqdn):
        resp = requests.delete(
            f"{self._base_url}/api/v1/services/{fqdn}",
            headers=self._headers(),
            timeout=10,
        )
        self._check(resp)

    def get_service_settings(self, fqdn):
        resp = requests.get(
            f"{self._base_url}/api/v1/services/{fqdn}/settings",
            headers=self._headers(),
            timeout=10,
        )
        self._check(resp)
        return resp.json()

    def update_service_settings(self, fqdn, settings: dict):
        resp = requests.patch(
            f"{self._base_url}/api/v1/services/{fqdn}/settings",
            headers=self._headers(),
            json=settings,
            timeout=10,
        )
        self._check(resp)
        return resp.json()

    def get_service_reports(self, fqdn):
        resp = requests.get(
            f"{self._base_url}/api/v1/services/{fqdn}/reports",
            headers=self._headers(),
            timeout=10,
        )
        self._check(resp)
        return resp.json()

    def list_services(self):
        resp = requests.get(
            f"{self._base_url}/api/v1/services",
            headers=self._headers(),
            timeout=10,
        )
        self._check(resp)
        return resp.json()
