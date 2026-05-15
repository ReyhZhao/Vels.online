from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.utils import timezone

from security.advisory import UbuntuAdvisoryClient, UbuntuAdvisoryError, get_or_fetch
from security.models import CveAdvisory

_CVE = "CVE-2023-0464"


# ---------------------------------------------------------------- helpers

def _ok(payload):
    m = MagicMock()
    m.status_code = 200
    m.ok = True
    m.json.return_value = payload
    m.raise_for_status = MagicMock()
    return m


def _not_found():
    m = MagicMock()
    m.status_code = 404
    m.ok = False
    return m


def _server_error():
    m = MagicMock()
    m.status_code = 500
    m.ok = False
    m.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
    return m


_UBUNTU_PAYLOAD = {
    "id": _CVE,
    "notices": [{"id": "USN-6037-1", "title": "OpenSSL vulnerabilities"}],
    "packages": [
        {
            "name": "openssl",
            "statuses": [
                {"release_codename": "jammy", "status": "released", "description": "3.0.2-0ubuntu1.10"},
                {"release_codename": "focal", "status": "released", "description": "1.1.1f-1ubuntu2.18"},
            ],
        }
    ],
}


# --------------------------------------------------------- UbuntuAdvisoryClient


@patch("security.advisory.requests.get")
def test_ubuntu_client_returns_advisory_on_valid_response(mock_get):
    mock_get.return_value = _ok(_UBUNTU_PAYLOAD)
    advisory_url, remediation_text, raw_data = UbuntuAdvisoryClient().fetch(_CVE)

    assert advisory_url == f"https://ubuntu.com/security/cve/{_CVE}"
    assert "USN-6037-1" in remediation_text
    assert "openssl" in remediation_text
    assert "jammy" in remediation_text
    assert raw_data == _UBUNTU_PAYLOAD
    mock_get.assert_called_once()
    assert _CVE in mock_get.call_args[0][0]


@patch("security.advisory.requests.get")
def test_ubuntu_client_returns_none_on_404(mock_get):
    mock_get.return_value = _not_found()
    advisory_url, remediation_text, raw_data = UbuntuAdvisoryClient().fetch(_CVE)

    assert advisory_url is None
    assert remediation_text is None
    assert raw_data is None


@patch("security.advisory.requests.get")
def test_ubuntu_client_raises_on_server_error(mock_get):
    mock_get.return_value = _server_error()
    with pytest.raises(UbuntuAdvisoryError):
        UbuntuAdvisoryClient().fetch(_CVE)


@patch("security.advisory.requests.get")
def test_ubuntu_client_returns_none_when_no_released_versions(mock_get):
    payload = {
        "id": _CVE,
        "notices": [],
        "packages": [
            {
                "name": "openssl",
                "statuses": [{"release_codename": "jammy", "status": "needed", "description": ""}],
            }
        ],
    }
    mock_get.return_value = _ok(payload)
    advisory_url, remediation_text, _ = UbuntuAdvisoryClient().fetch(_CVE)

    assert advisory_url is None
    assert remediation_text is None


# --------------------------------------------------------- get_or_fetch (AdvisoryService)


@pytest.mark.django_db
@patch("security.advisory.UbuntuAdvisoryClient")
def test_get_or_fetch_returns_cached_fresh_row(MockClient):
    CveAdvisory.objects.create(
        cve_id=_CVE,
        platform="ubuntu",
        advisory_url="https://ubuntu.com/security/cve/CVE-2023-0464",
        remediation_text="Run apt-get upgrade.",
        fetched_at=timezone.now() - timedelta(days=1),
    )

    result = get_or_fetch(_CVE, "ubuntu")

    MockClient.assert_not_called()
    assert result.advisory_url == "https://ubuntu.com/security/cve/CVE-2023-0464"


@pytest.mark.django_db
@patch("security.advisory.UbuntuAdvisoryClient")
def test_get_or_fetch_fetches_on_cache_miss(MockClient):
    MockClient.return_value.fetch.return_value = (
        "https://ubuntu.com/security/cve/CVE-2023-0464",
        "Run apt-get upgrade openssl.",
        _UBUNTU_PAYLOAD,
    )

    result = get_or_fetch(_CVE, "ubuntu")

    MockClient.return_value.fetch.assert_called_once_with(_CVE)
    assert result.advisory_url == "https://ubuntu.com/security/cve/CVE-2023-0464"
    assert CveAdvisory.objects.filter(cve_id=_CVE, platform="ubuntu").exists()


@pytest.mark.django_db
@patch("security.advisory.UbuntuAdvisoryClient")
def test_get_or_fetch_refetches_stale_row(MockClient):
    CveAdvisory.objects.create(
        cve_id=_CVE,
        platform="ubuntu",
        advisory_url="https://ubuntu.com/security/cve/CVE-2023-0464",
        remediation_text="Old text.",
        fetched_at=timezone.now() - timedelta(days=8),
    )
    MockClient.return_value.fetch.return_value = (
        "https://ubuntu.com/security/cve/CVE-2023-0464",
        "Updated remediation text.",
        _UBUNTU_PAYLOAD,
    )

    result = get_or_fetch(_CVE, "ubuntu")

    MockClient.return_value.fetch.assert_called_once_with(_CVE)
    assert result.remediation_text == "Updated remediation text."


@pytest.mark.django_db
@patch("security.advisory.UbuntuAdvisoryClient")
def test_get_or_fetch_stores_null_when_no_advisory(MockClient):
    MockClient.return_value.fetch.return_value = (None, None, None)

    result = get_or_fetch(_CVE, "ubuntu")

    assert result.advisory_url is None
    assert result.remediation_text is None
    assert CveAdvisory.objects.filter(cve_id=_CVE, platform="ubuntu").exists()


@pytest.mark.django_db
@patch("security.advisory.UbuntuAdvisoryClient")
def test_get_or_fetch_returns_stale_row_on_client_exception(MockClient):
    stale = CveAdvisory.objects.create(
        cve_id=_CVE,
        platform="ubuntu",
        advisory_url="https://ubuntu.com/security/cve/CVE-2023-0464",
        remediation_text="Stale text.",
        fetched_at=timezone.now() - timedelta(days=10),
    )
    MockClient.return_value.fetch.side_effect = UbuntuAdvisoryError("API down")

    result = get_or_fetch(_CVE, "ubuntu")

    assert result.pk == stale.pk
    assert result.remediation_text == "Stale text."


@pytest.mark.django_db
@patch("security.advisory.UbuntuAdvisoryClient")
def test_get_or_fetch_returns_null_advisory_on_exception_no_stale(MockClient):
    MockClient.return_value.fetch.side_effect = UbuntuAdvisoryError("API down")

    result = get_or_fetch(_CVE, "ubuntu")

    assert result.advisory_url is None
    assert result.pk is None
    assert not CveAdvisory.objects.filter(cve_id=_CVE, platform="ubuntu").exists()


@pytest.mark.django_db
@patch("security.advisory.UbuntuAdvisoryClient")
def test_get_or_fetch_skips_fetch_for_unsupported_platform(MockClient):
    result = get_or_fetch(_CVE, "windows")

    MockClient.assert_not_called()
    assert result.advisory_url is None
