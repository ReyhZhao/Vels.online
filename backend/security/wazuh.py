import os

import requests
import urllib3
from django.core.cache import cache

# Wazuh uses self-signed TLS internally; suppress the resulting warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_TOKEN_CACHE_KEY = "wazuh_jwt_token"
_TOKEN_CACHE_TTL = 800  # Wazuh tokens expire at 900s; cache slightly shorter


class WazuhAuthError(RuntimeError):
    pass


class WazuhAPIError(RuntimeError):
    pass


class WazuhClient:
    def __init__(self):
        self._base_url = os.environ.get("WAZUH_API_URL", "").rstrip("/")
        self._user = os.environ.get("WAZUH_API_USER", "")
        self._password = os.environ.get("WAZUH_API_PASSWORD", "")

    # ------------------------------------------------------------------ auth

    def _fetch_token(self):

        if not self._user or not self._password:
            raise Exception("Username or password not set in environment variables.")

        response = requests.post(
            f"{self._base_url}/security/user/authenticate",
            auth=(self._user, self._password),
            verify=False,
            timeout=10,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise WazuhAuthError(f"Wazuh authentication failed: {exc}") from exc
        data = response.json()
        if data.get("error") != 0:
            raise WazuhAuthError(f"Wazuh authentication failed: {data.get('message', 'unknown')}")
        return data["data"]["token"]

    def _get_token(self):
        token = cache.get(_TOKEN_CACHE_KEY)
        if token:
            return token
        token = self._fetch_token()
        cache.set(_TOKEN_CACHE_KEY, token, _TOKEN_CACHE_TTL)
        return token

    def _headers(self):
        return {"Authorization": f"Bearer {self._get_token()}"}

    # ---------------------------------------------------------------- helpers

    def _get(self, path, params=None):
        response = requests.get(
            f"{self._base_url}{path}",
            headers=self._headers(),
            params=params,
            verify=False,
            timeout=10,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise WazuhAPIError(f"Wazuh API error on {path}: {exc}") from exc
        data = response.json()
        if data.get("error") != 0:
            raise WazuhAPIError(f"Wazuh API error on {path}: {data.get('message', 'unknown')}")
        return data

    def _post(self, path, body):
        response = requests.post(
            f"{self._base_url}{path}",
            headers=self._headers(),
            json=body,
            verify=False,
            timeout=10,
        )
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise WazuhAPIError(f"Wazuh API error on {path}: {exc}") from exc
        data = response.json()
        if data.get("error") != 0:
            raise WazuhAPIError(f"Wazuh API error on {path}: {data.get('message', 'unknown')}")
        return data

    # --------------------------------------------------------- public methods

    def create_group(self, group_name):
        self._post("/groups", {"group_id": group_name})

    def get_agents(self, group_name):
        data = self._get(
            "/agents",
            params={
                "groups_list": group_name,
                "select": "id,name,ip,status,os.name,os.version,os.platform,lastKeepAlive",
                "limit": 500,
            },
        )
        return data["data"]["affected_items"]

    def get_agent_events(self, agent_id, hours=24, offset=0, limit=100):
        data = self._get(
            "/events",
            params={
                "agent_ids": agent_id,
                "q": f"timestamp>{hours}h",
                "offset": offset,
                "limit": limit,
            },
        )
        return {
            "events": data["data"]["affected_items"],
            "total": data["data"]["total_affected_items"],
        }

    def get_agent_vulnerabilities(self, agent_id, offset=0, limit=50):
        data = self._get(
            f"/vulnerability/{agent_id}",
            params={"offset": offset, "limit": limit},
        )
        return {
            "vulnerabilities": data["data"]["affected_items"],
            "total": data["data"]["total_affected_items"],
        }

    def get_vulnerabilities_summary(self, agents):
        """Return {critical, high, medium, low} counts across the given agent list."""
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for agent in agents:
            if agent.get("status") != "active":
                continue
            for severity in counts:
                try:
                    data = self._get(
                        f"/vulnerability/{agent['id']}",
                        params={"severity": severity, "limit": 1},
                    )
                    counts[severity] += data["data"]["total_affected_items"]
                except WazuhAPIError:
                    pass
        return counts

    def get_events_count(self, agents, hours=24):
        """Return total security event count for the given agent list in the last N hours."""
        total = 0
        for agent in agents:
            if agent.get("status") != "active":
                continue
            try:
                data = self._get(
                    "/events",
                    params={"agent_ids": agent["id"], "q": f"timestamp>{hours}h", "limit": 1},
                )
                total += data["data"]["total_affected_items"]
            except WazuhAPIError:
                pass
        return total
