"""Tests for IOC enrichment service (AbuseIPDB + VirusTotal) and coordinator task."""
import pytest
from unittest.mock import MagicMock, patch

from security.models import Organization, OrganizationMembership
from incidents.models import IOC, Incident


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def acme(db):
    return Organization.objects.create(name="Acme", slug="acme", wazuh_group="acme")


def make_incident(acme):
    count = Incident.objects.count()
    return Incident.objects.create(
        organization=acme,
        title="Test incident",
        display_id=f"INC-2026-{count + 1:04d}",
        state="new",
    )


def make_ioc(incident, kind, value, enrichment_data=None):
    return IOC.objects.create(
        incident=incident,
        kind=kind,
        value=value,
        enrichment_data=enrichment_data or {},
    )


def _abuseipdb_success_response(score=87, reports=142, country="CN", usage="Data Center/Web Hosting/Transit"):
    return {
        "data": {
            "abuseConfidenceScore": score,
            "totalReports": reports,
            "countryCode": country,
            "usageType": usage,
        }
    }


def _virustotal_success_response(malicious=12, suspicious=2, total=94):
    stats = {"malicious": malicious, "suspicious": suspicious, "undetected": total - malicious - suspicious}
    return {"data": {"attributes": {"last_analysis_stats": stats}}}


# ── enrich_ioc — AbuseIPDB ───────────────────────────────────────────────────


@pytest.mark.django_db
def test_enrich_ioc_returns_abuseipdb_data_for_ip(acme):
    from incidents.services.ioc_enrichment import enrich_ioc

    incident = make_incident(acme)
    ioc = make_ioc(incident, "ip", "185.220.101.5")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _abuseipdb_success_response()

    with patch("incidents.services.ioc_enrichment.requests.get", return_value=mock_resp):
        with patch("django.conf.settings.ABUSEIPDB_API_KEY", "test-key"):
            result = enrich_ioc(ioc)

    assert result["abuseipdb"]["status"] == "done"
    assert result["abuseipdb"]["abuse_confidence_score"] == 87
    assert result["abuseipdb"]["total_reports"] == 142
    assert result["abuseipdb"]["country_code"] == "CN"
    assert result["abuseipdb"]["usage_type"] == "Data Center/Web Hosting/Transit"


@pytest.mark.django_db
def test_enrich_ioc_returns_cached_result_without_http_call(acme):
    from incidents.services.ioc_enrichment import enrich_ioc, _cache_key

    incident = make_incident(acme)
    ioc = make_ioc(incident, "ip", "1.2.3.4")
    cached = {"abuseipdb": {"status": "done", "abuse_confidence_score": 50}}

    with patch("incidents.services.ioc_enrichment.cache.get", return_value=cached):
        with patch("incidents.services.ioc_enrichment.requests.get") as mock_get:
            with patch("django.conf.settings.ABUSEIPDB_API_KEY", "test-key"):
                result = enrich_ioc(ioc)

    mock_get.assert_not_called()
    assert result == cached


@pytest.mark.django_db
def test_enrich_ioc_rate_limited_returns_failed_no_retry(acme):
    from incidents.services.ioc_enrichment import enrich_ioc

    incident = make_incident(acme)
    ioc = make_ioc(incident, "ip", "1.2.3.4")

    mock_resp = MagicMock()
    mock_resp.status_code = 429

    with patch("incidents.services.ioc_enrichment.requests.get", return_value=mock_resp) as mock_get:
        with patch("django.conf.settings.ABUSEIPDB_API_KEY", "test-key"):
            with patch("incidents.services.ioc_enrichment.cache.get", return_value=None):
                result = enrich_ioc(ioc)

    mock_get.assert_called_once()
    assert result["abuseipdb"]["status"] == "failed"
    assert result["abuseipdb"]["error"] == "rate_limited"


@pytest.mark.django_db
def test_enrich_ioc_retries_on_5xx_and_returns_failed(acme):
    from incidents.services.ioc_enrichment import enrich_ioc

    incident = make_incident(acme)
    ioc = make_ioc(incident, "ip", "1.2.3.4")

    mock_resp = MagicMock()
    mock_resp.status_code = 503

    with patch("incidents.services.ioc_enrichment.requests.get", return_value=mock_resp) as mock_get:
        with patch("django.conf.settings.ABUSEIPDB_API_KEY", "test-key"):
            with patch("incidents.services.ioc_enrichment.cache.get", return_value=None):
                with patch("incidents.services.ioc_enrichment.time.sleep"):
                    result = enrich_ioc(ioc)

    assert mock_get.call_count == 3  # _MAX_RETRIES
    assert result["abuseipdb"]["status"] == "failed"


@pytest.mark.django_db
def test_enrich_ioc_returns_empty_and_logs_when_no_api_key(acme, caplog):
    from incidents.services.ioc_enrichment import enrich_ioc
    import logging

    incident = make_incident(acme)
    ioc = make_ioc(incident, "ip", "1.2.3.4")

    with patch("incidents.services.ioc_enrichment.cache.get", return_value=None):
        with patch("django.conf.settings.ABUSEIPDB_API_KEY", None):
            with caplog.at_level(logging.WARNING, logger="incidents.services.ioc_enrichment"):
                result = enrich_ioc(ioc)

    assert result == {}
    assert any("ABUSEIPDB_API_KEY" in r.message for r in caplog.records)


# ── enrich_ioc — VirusTotal ──────────────────────────────────────────────────


@pytest.mark.django_db
def test_enrich_ioc_returns_virustotal_data_for_domain(acme):
    from incidents.services.ioc_enrichment import enrich_ioc

    incident = make_incident(acme)
    ioc = make_ioc(incident, "domain", "malicious.example.com")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _virustotal_success_response(malicious=12, suspicious=2, total=94)

    with patch("incidents.services.ioc_enrichment.requests.get", return_value=mock_resp):
        with patch("django.conf.settings.VIRUSTOTAL_API_KEY", "test-key"):
            with patch("incidents.services.ioc_enrichment.cache.get", return_value=None):
                result = enrich_ioc(ioc)

    assert result["virustotal"]["status"] == "done"
    assert result["virustotal"]["malicious"] == 12
    assert result["virustotal"]["suspicious"] == 2


@pytest.mark.django_db
def test_enrich_ioc_returns_virustotal_data_for_url(acme):
    from incidents.services.ioc_enrichment import enrich_ioc

    incident = make_incident(acme)
    ioc = make_ioc(incident, "url", "http://malicious.example.com/payload")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _virustotal_success_response(malicious=5, suspicious=1, total=70)

    with patch("incidents.services.ioc_enrichment.requests.get", return_value=mock_resp):
        with patch("django.conf.settings.VIRUSTOTAL_API_KEY", "test-key"):
            with patch("incidents.services.ioc_enrichment.cache.get", return_value=None):
                result = enrich_ioc(ioc)

    assert result["virustotal"]["status"] == "done"
    assert result["virustotal"]["malicious"] == 5


@pytest.mark.django_db
def test_enrich_ioc_domain_cache_hit_avoids_api(acme):
    from incidents.services.ioc_enrichment import enrich_ioc

    incident = make_incident(acme)
    ioc = make_ioc(incident, "domain", "example.com")
    cached = {"virustotal": {"status": "done", "malicious": 0, "suspicious": 0, "total": 50}}

    with patch("incidents.services.ioc_enrichment.cache.get", return_value=cached):
        with patch("incidents.services.ioc_enrichment.requests.get") as mock_get:
            with patch("django.conf.settings.VIRUSTOTAL_API_KEY", "test-key"):
                result = enrich_ioc(ioc)

    mock_get.assert_not_called()
    assert result == cached


@pytest.mark.django_db
def test_enrich_ioc_virustotal_rate_limited(acme):
    from incidents.services.ioc_enrichment import enrich_ioc

    incident = make_incident(acme)
    ioc = make_ioc(incident, "domain", "example.com")

    mock_resp = MagicMock()
    mock_resp.status_code = 429

    with patch("incidents.services.ioc_enrichment.requests.get", return_value=mock_resp) as mock_get:
        with patch("django.conf.settings.VIRUSTOTAL_API_KEY", "test-key"):
            with patch("incidents.services.ioc_enrichment.cache.get", return_value=None):
                result = enrich_ioc(ioc)

    mock_get.assert_called_once()
    assert result["virustotal"]["status"] == "failed"
    assert result["virustotal"]["error"] == "rate_limited"


@pytest.mark.django_db
def test_enrich_ioc_returns_empty_and_logs_when_no_virustotal_key(acme, caplog):
    from incidents.services.ioc_enrichment import enrich_ioc
    import logging

    incident = make_incident(acme)
    ioc = make_ioc(incident, "domain", "example.com")

    with patch("incidents.services.ioc_enrichment.cache.get", return_value=None):
        with patch("django.conf.settings.VIRUSTOTAL_API_KEY", None):
            with caplog.at_level(logging.WARNING, logger="incidents.services.ioc_enrichment"):
                result = enrich_ioc(ioc)

    assert result == {}
    assert any("VIRUSTOTAL_API_KEY" in r.message for r in caplog.records)


@pytest.mark.django_db
def test_enrich_ioc_returns_empty_for_unknown_kind(acme):
    from incidents.services.ioc_enrichment import enrich_ioc

    incident = make_incident(acme)
    ioc = make_ioc(incident, "ip", "1.2.3.4")
    ioc.kind = "hash"  # not a real kind but simulate it

    result = enrich_ioc(ioc)
    assert result == {}


# ── coordinator task ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_coordinator_enriches_iocs_and_dispatches_triage(acme):
    from incidents.tasks import enrich_iocs_then_triage

    incident = make_incident(acme)
    ioc = make_ioc(incident, "ip", "1.2.3.4")

    enrichment_result = {"abuseipdb": {"status": "done", "abuse_confidence_score": 42}}

    with patch("incidents.services.ioc_enrichment.enrich_ioc", return_value=enrichment_result) as mock_enrich:
        with patch("incidents.tasks.run_incident_triage") as mock_triage:
            mock_triage.delay = MagicMock()
            enrich_iocs_then_triage.apply(args=(incident.id,))

    mock_enrich.assert_called_once()
    ioc.refresh_from_db()
    assert ioc.enrichment_data == enrichment_result
    mock_triage.delay.assert_called_once_with(incident.id)


@pytest.mark.django_db
def test_coordinator_dispatches_triage_even_if_enrichment_fails(acme):
    from incidents.tasks import enrich_iocs_then_triage

    incident = make_incident(acme)
    make_ioc(incident, "ip", "1.2.3.4")

    with patch("incidents.services.ioc_enrichment.enrich_ioc", side_effect=Exception("network error")):
        with patch("incidents.tasks.run_incident_triage") as mock_triage:
            mock_triage.delay = MagicMock()
            enrich_iocs_then_triage.apply(args=(incident.id,))

    mock_triage.delay.assert_called_once_with(incident.id)


@pytest.mark.django_db
def test_coordinator_dispatches_triage_with_no_iocs(acme):
    from incidents.tasks import enrich_iocs_then_triage

    incident = make_incident(acme)

    with patch("incidents.tasks.run_incident_triage") as mock_triage:
        mock_triage.delay = MagicMock()
        enrich_iocs_then_triage.apply(args=(incident.id,))

    mock_triage.delay.assert_called_once_with(incident.id)


# ── _build_triage_payload enrichment annotations ─────────────────────────────


@pytest.mark.django_db
def test_build_triage_payload_includes_annotation_for_ip_with_abuseipdb(acme):
    from incidents.tasks import _build_triage_payload

    incident = make_incident(acme)
    enrichment = {
        "abuseipdb": {
            "status": "done",
            "abuse_confidence_score": 87,
            "total_reports": 142,
            "country_code": "CN",
            "usage_type": "Data Center/Web Hosting/Transit",
        }
    }
    make_ioc(incident, "ip", "185.220.101.5", enrichment_data=enrichment)
    incident.refresh_from_db()

    payload = _build_triage_payload(incident)
    ioc_values = [i["value"] for i in payload["iocs"]]
    assert any("AbuseIPDB: 87/100" in v for v in ioc_values)


@pytest.mark.django_db
def test_build_triage_payload_omits_annotation_for_empty_enrichment(acme):
    from incidents.tasks import _build_triage_payload

    incident = make_incident(acme)
    make_ioc(incident, "ip", "10.0.0.1", enrichment_data={})
    incident.refresh_from_db()

    payload = _build_triage_payload(incident)
    ioc_values = [i["value"] for i in payload["iocs"]]
    assert ioc_values == ["10.0.0.1"]


@pytest.mark.django_db
def test_build_triage_payload_omits_annotation_for_failed_enrichment(acme):
    from incidents.tasks import _build_triage_payload

    incident = make_incident(acme)
    enrichment = {"abuseipdb": {"status": "failed", "error": "rate_limited"}}
    make_ioc(incident, "ip", "10.0.0.1", enrichment_data=enrichment)
    incident.refresh_from_db()

    payload = _build_triage_payload(incident)
    ioc_values = [i["value"] for i in payload["iocs"]]
    assert ioc_values == ["10.0.0.1"]


# ── PromoteView IOC extraction ────────────────────────────────────────────────


@pytest.fixture
def staff_user(db, django_user_model):
    return django_user_model.objects.create_user(
        username="staff", password="pass", is_staff=True
    )


@pytest.mark.django_db
def test_promote_view_extracts_iocs(client, staff_user, acme):
    """PromoteView should extract IOCs when committing."""
    client.force_login(staff_user)

    with patch("incidents.views.acquire_triage_lock", return_value=False):
        response = client.post("/api/incidents/promote/", {
            "source_kind": "wazuh_event",
            "source_ref": {},
            "commit": True,
            "org": "acme",
            "title": "Test — attacker at 185.220.101.5 connected",
            "severity": "high",
        }, content_type="application/json")

    assert response.status_code == 201
    data = response.json()
    iocs = IOC.objects.filter(incident_id=data["id"])
    ip_iocs = iocs.filter(kind="ip")
    assert ip_iocs.filter(value="185.220.101.5").exists()
