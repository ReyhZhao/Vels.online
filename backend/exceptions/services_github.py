"""Push / update an ExceptionRule's XML element in the security-monitoring repo."""
import base64
import re
import xml.etree.ElementTree as ET

import requests
from django.conf import settings

from .services_xml import rule_file_path, rule_to_xml

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


def _upsert_rule_element(xml_content: str, rule_xml: str, rule_id: int) -> str:
    """Insert or replace the <rule id="{rule_id}"> element within xml_content."""
    new_elem = ET.fromstring(rule_xml)

    # Strip and re-parse the existing document
    root = ET.fromstring(xml_content.strip() or _EMPTY_FILE)

    # Remove any existing rule with the same ID
    for existing in root.findall(f"rule[@id='{rule_id}']"):
        root.remove(existing)

    root.append(new_elem)
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def _remove_rule_element(xml_content: str, rule_id: int) -> str:
    """Remove the <rule id="{rule_id}"> element from xml_content."""
    root = ET.fromstring(xml_content.strip() or _EMPTY_FILE)
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

    updated = _remove_rule_element(content, rule.wazuh_rule_id)
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


def push_rule(rule) -> None:
    """Commit the rule's XML element to the security-monitoring repo."""
    path    = rule_file_path(rule)
    xml_str = rule_to_xml(rule)

    content, sha = _get_file(path)
    if content is None:
        content = _EMPTY_FILE

    updated = _upsert_rule_element(content, xml_str, rule.wazuh_rule_id)
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
