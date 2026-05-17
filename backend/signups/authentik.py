import requests
from django.conf import settings
from requests.exceptions import RequestException


class AuthentikAPIError(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Authentik API error {status_code}: {body}")


class AuthentikClient:
    def __init__(self):
        self._base_url = settings.AUTHENTIK_API_URL.rstrip("/")
        self._token = settings.AUTHENTIK_API_TOKEN

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _check(self, response):
        if not response.ok:
            raise AuthentikAPIError(response.status_code, response.text)
        return response

    def _post(self, path, **kwargs):
        try:
            return requests.post(
                f"{self._base_url}/api/v3{path}",
                headers=self._headers(),
                timeout=10,
                **kwargs,
            )
        except RequestException as exc:
            raise AuthentikAPIError(0, str(exc)) from exc

    def _get(self, path, **kwargs):
        try:
            return requests.get(
                f"{self._base_url}/api/v3{path}",
                headers=self._headers(),
                timeout=10,
                **kwargs,
            )
        except RequestException as exc:
            raise AuthentikAPIError(0, str(exc)) from exc

    def _delete(self, path, **kwargs):
        try:
            return requests.delete(
                f"{self._base_url}/api/v3{path}",
                headers=self._headers(),
                timeout=10,
                **kwargs,
            )
        except RequestException as exc:
            raise AuthentikAPIError(0, str(exc)) from exc

    def create_group(self, name):
        resp = self._post("/core/groups/", json={"name": name})
        self._check(resp)
        return resp.json()["pk"]

    def find_group_by_name(self, name):
        """Return the group PK if a group with this name exists, else None."""
        resp = self._get("/core/groups/", params={"name": name})
        self._check(resp)
        results = resp.json().get("results", [])
        return results[0]["pk"] if results else None

    def delete_group(self, pk):
        resp = self._delete(f"/core/groups/{pk}/")
        if resp.status_code == 404:
            return
        self._check(resp)

    def get_flow_uuid(self, slug):
        resp = self._get("/flows/instances/", params={"slug": slug})
        self._check(resp)
        results = resp.json().get("results", [])
        if not results:
            raise AuthentikAPIError(0, f"No flow found with slug '{slug}'")
        return results[0]["pk"]

    def create_invitation(self, flow_uuid, expires_at, name):
        resp = self._post(
            "/stages/invitation/invitations/",
            json={
                "name": name,
                "flow": flow_uuid,
                "expires": expires_at.isoformat(),
                "single_use": True,
            },
        )
        self._check(resp)
        data = resp.json()
        # pk is the UUID that acts as the invite token
        return {"pk": data["pk"], "token": data["pk"]}

    def delete_invitation(self, pk):
        resp = self._delete(f"/stages/invitation/invitations/{pk}/")
        if resp.status_code == 404:
            return
        self._check(resp)

    def build_invite_url(self, flow_slug, token):
        return f"{self._base_url}/if/flow/{flow_slug}/?itoken={token}"
