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

    def _put(self, path, body, params=None):
        response = requests.put(
            f"{self._base_url}{path}",
            headers=self._headers(),
            json=body,
            params=params,
            verify=False,
            timeout=10,
        )
        status_code = response.status_code
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise WazuhAPIError(f"Wazuh API error on {path}: {exc}") from exc
        data = response.json()
        if data.get("error") != 0:
            raise WazuhAPIError(f"Wazuh API error on {path}: {data.get('message', 'unknown')}")
        return status_code, data

    def create_group(self, group_name):
        self._post("/groups", {"group_id": group_name})

    def get_agents(self, group_name):
        data = self._get(
            "/agents",
            params={
                "group": group_name,
                "select": "id,name,ip,status,os.name,os.version,os.platform,lastKeepAlive",
                "limit": 500,
            },
        )
        return data["data"]["affected_items"]

    def restart_manager(self):
        """Send PUT /manager/restart to reload Wazuh rules without rebooting."""
        self._put("/manager/restart", {})

    def get_agent_processes(self, agent_id):
        """Live running processes on an agent (syscollector). Used by Hunt lenses."""
        data = self._get(
            f"/syscollector/{agent_id}/processes",
            params={"select": "pid,name,state,ppid,cmd,euser", "limit": 500},
        )
        return data["data"]["affected_items"]

    def get_agent_ports(self, agent_id):
        """Open ports / listening services on an agent (syscollector). Used by Hunt lenses."""
        data = self._get(
            f"/syscollector/{agent_id}/ports",
            params={"select": "local.ip,local.port,protocol,state,process,pid", "limit": 500},
        )
        return data["data"]["affected_items"]

    def run_active_response(self, command, agent_ids, args="", timeout=0):
        """Send PUT /active-response to dispatch a command against agent_ids.

        Returns (status_code, response_body). Raises WazuhAPIError on non-2xx.
        Wazuh expects agent IDs as strings in the agents_list array.
        """
        body = {
            "command": command,
            "arguments": args.split() if args else [],
            "agents_list": [str(a) for a in agent_ids],
        }
        if timeout:
            body["timeout"] = timeout
        params = {"wait_for_complete": "false"}
        return self._put("/active-response", body, params=params)

