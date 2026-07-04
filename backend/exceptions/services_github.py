"""Push / update an ExceptionRule's XML element in the security-monitoring repo."""
import base64
import logging
import re
import xml.etree.ElementTree as ET
from io import StringIO

import requests
from django.conf import settings
from ruamel.yaml import YAML

from .services_xml import rule_file_path, rule_to_xml

logger = logging.getLogger(__name__)

REPO        = "ReyhZhao/argocd-deployments"
BRANCH      = "main"
API_BASE    = f"https://api.github.com/repos/{REPO}/contents"
_EMPTY_FILE = '<?xml version="1.0" encoding="UTF-8"?>\n<group name="exceptions">\n</group>\n'


def _headers():
    token = getattr(settings, "WAZUH_RULES_GITHUB_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _get_file(path: str):
    """Return (content_str, sha) or (None, None) if the file doesn't exist."""
    resp = requests.get(f"{API_BASE}/{path}", headers=_headers(), timeout=15)
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()
    data = resp.json()
    content = base64.b64decode(data["content"]).decode()
    return content, data["sha"]


def _parse_group(xml_content: str, path: str = "") -> ET.Element:
    """Parse *xml_content* into its <group> root element.

    The exception files this service owns are single-rooted
    ``<group name="exceptions">`` documents. If the fetched content is empty,
    whitespace-only, comment-only, or otherwise not parseable as a single root
    element, fall back to a fresh empty exceptions group rather than letting an
    ``ET.ParseError`` propagate and 502 the request (issue #650 — e.g. a file
    whose entire body is wrapped in an XML comment).
    """
    stripped = xml_content.strip()
    if stripped:
        try:
            return ET.fromstring(stripped)
        except ET.ParseError as exc:
            logger.warning(
                "Existing exceptions file %r was not parseable (%s); "
                "replacing it with a fresh empty exceptions group.",
                path or "<unknown>", exc,
            )
    return ET.fromstring(_EMPTY_FILE)


def _upsert_rule_element(xml_content: str, rule_xml: str, rule_id: int, path: str = "") -> str:
    """Insert or replace the <rule id="{rule_id}"> element within xml_content."""
    new_elem = ET.fromstring(rule_xml)

    # Strip and re-parse the existing document (resilient to unparseable content)
    root = _parse_group(xml_content, path)

    # Remove any existing rule with the same ID
    for existing in root.findall(f"rule[@id='{rule_id}']"):
        root.remove(existing)

    root.append(new_elem)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _remove_rule_element(xml_content: str, rule_id: int, path: str = "") -> str:
    """Remove the <rule id="{rule_id}"> element from xml_content."""
    root = _parse_group(xml_content, path)
    for existing in root.findall(f"rule[@id='{rule_id}']"):
        root.remove(existing)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def remove_rule(rule) -> None:
    """Remove the rule's XML element from the security-monitoring repo."""
    path = rule_file_path(rule)
    content, sha = _get_file(path)
    if content is None or sha is None:
        return  # File doesn't exist — nothing to remove

    updated = _remove_rule_element(content, rule.wazuh_rule_id, path)
    encoded = base64.b64encode(updated.encode()).decode()

    payload = {
        "message": f"exception: remove rule {rule.wazuh_rule_id} — {rule.description[:60]}",
        "content": encoded,
        "branch": BRANCH,
        "sha": sha,
    }

    resp = requests.put(
        f"{API_BASE}/{path}",
        json=payload,
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()


_APPS_VALUES_PATH = "wazuh/apps-values.yaml"
_RULE_VOLUME_NAME = "dynamic-rule-config"
_RULES_CONFIGMAP  = "rules-configmap"


def _ensure_volume_mount(file_path: str) -> None:
    """Add additionalVolumeMounts (and additionalVolumes if absent) for *file_path*
    to both master and worker sections of apps-values.yaml."""
    filename = file_path.split("/")[-1]

    content, sha = _get_file(_APPS_VALUES_PATH)
    if content is None or sha is None:
        return

    ryaml = YAML()
    ryaml.preserve_quotes = True
    data = ryaml.load(content)

    new_volume = {"name": _RULE_VOLUME_NAME, "configMap": {"name": _RULES_CONFIGMAP}}
    new_mount  = {
        "name":       _RULE_VOLUME_NAME,
        "mountPath":  f"/wazuh-config-mount/etc/rules/{filename}",
        "subPath":    filename,
    }

    changed = False
    master = data["wazuh"]["wazuh"]["master"]

    volumes = master.get("additionalVolumes") or []
    if not any(v.get("name") == _RULE_VOLUME_NAME for v in volumes):
        if "additionalVolumes" not in master or master["additionalVolumes"] is None:
            master["additionalVolumes"] = [new_volume]
        else:
            master["additionalVolumes"].append(new_volume)
        changed = True

    mounts = master.get("additionalVolumeMounts") or []
    if not any(m.get("subPath") == filename for m in mounts):
        if "additionalVolumeMounts" not in master or master["additionalVolumeMounts"] is None:
            master["additionalVolumeMounts"] = [new_mount]
        else:
            master["additionalVolumeMounts"].append(new_mount)
        changed = True

    if not changed:
        return

    buf = StringIO()
    ryaml.dump(data, buf)
    encoded = base64.b64encode(buf.getvalue().encode()).decode()

    resp = requests.put(
        f"{API_BASE}/{_APPS_VALUES_PATH}",
        json={
            "message": f"exception: add {filename} volume mount to Wazuh deployment",
            "content": encoded,
            "branch":  BRANCH,
            "sha":     sha,
        },
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()


def push_rule(rule) -> None:
    """Commit the rule's XML element to the security-monitoring repo."""
    path    = rule_file_path(rule)
    xml_str = rule_to_xml(rule)

    content, sha = _get_file(path)
    is_new_file = sha is None
    if content is None:
        content = _EMPTY_FILE

    updated = _upsert_rule_element(content, xml_str, rule.wazuh_rule_id, path)
    encoded = base64.b64encode(updated.encode()).decode()

    payload = {
        "message": f"exception: add rule {rule.wazuh_rule_id} — {rule.description[:60]}",
        "content": encoded,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    resp = requests.put(
        f"{API_BASE}/{path}",
        json=payload,
        headers=_headers(),
        timeout=15,
    )
    resp.raise_for_status()

    if is_new_file:
        _ensure_volume_mount(path)
