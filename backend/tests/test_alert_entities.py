import pytest
from security.models import Organization
from alerts.models import Alert, AlertEntity
from alerts.services.entities import canonicalize, entities_for


@pytest.fixture
def acme(db):
    return Organization.objects.create(
        name="Acme", slug="acme", wazuh_group="acme", alert_match_lookback_days=30
    )


def _make_alert(org):
    count = Alert.objects.count()
    return Alert.objects.create(
        organization=org,
        display_id=f"AL-ENT-{count + 1:04d}",
        source_kind="wazuh_event",
        source_ref={},
        title="Test",
        severity="medium",
    )


# ---------------------------------------------------------------------------
# canonicalize()
# ---------------------------------------------------------------------------

class TestCanonicalize:
    def test_casefolds_hostname(self):
        assert canonicalize("host.name", "WEB-PROD-01") == "web-prod-01"

    def test_casefolds_ip(self):
        assert canonicalize("source.ip", "192.168.1.1") == "192.168.1.1"

    def test_casefolds_process(self):
        assert canonicalize("process.name", "SVCHOST.EXE") == "svchost.exe"

    def test_user_plain(self):
        assert canonicalize("user.name", "alice") == "alice"

    def test_user_domain_backslash(self):
        assert canonicalize("user.name", "CORP\\alice") == "alice"

    def test_user_domain_backslash_lowercase(self):
        assert canonicalize("user.name", "corp\\alice") == "alice"

    def test_user_at_domain(self):
        assert canonicalize("user.name", "alice@corp.example.com") == "alice"

    def test_user_at_domain_uppercase(self):
        assert canonicalize("user.name", "Alice@CORP.EXAMPLE.COM") == "alice"

    def test_user_domain_backslash_uppercase_user(self):
        assert canonicalize("user.name", "CORP\\Alice") == "alice"

    def test_three_formats_collapse_to_same(self):
        plain = canonicalize("user.name", "alice")
        backslash = canonicalize("user.name", "CORP\\alice")
        at_domain = canonicalize("user.name", "alice@corp.example.com")
        assert plain == backslash == at_domain

    def test_strips_whitespace(self):
        assert canonicalize("user.name", "  alice  ") == "alice"

    def test_hash_casefolds(self):
        sha = "A" * 64
        assert canonicalize("file.hash.sha256", sha) == "a" * 64


# ---------------------------------------------------------------------------
# entities_for()
# ---------------------------------------------------------------------------

class TestEntitiesFor:
    def test_empty_envelope(self):
        assert entities_for({}) == []

    def test_missing_envelope_key(self):
        assert entities_for({"source_kind": "wazuh_event"}) == []

    def test_none_envelope(self):
        assert entities_for({"entities": None}) == []

    def test_extracts_known_fields(self):
        payload = {"entities": {"host.name": "WEB-01", "source.ip": "10.0.0.1"}}
        result = entities_for(payload)
        assert ("host.name", "web-01") in result
        assert ("source.ip", "10.0.0.1") in result

    def test_ignores_unknown_fields(self):
        payload = {"entities": {"host.name": "web-01", "host.group": "dmz"}}
        result = entities_for(payload)
        assert len(result) == 1
        assert result[0][0] == "host.name"

    def test_ignores_empty_values(self):
        payload = {"entities": {"host.name": "", "user.name": "alice"}}
        result = entities_for(payload)
        assert len(result) == 1
        assert result[0] == ("user.name", "alice")

    def test_all_five_ecs_fields(self):
        payload = {
            "entities": {
                "host.name": "web-01",
                "source.ip": "1.2.3.4",
                "user.name": "CORP\\alice",
                "file.hash.sha256": "A" * 64,
                "process.name": "CMD.EXE",
            }
        }
        result = dict(entities_for(payload))
        assert result["host.name"] == "web-01"
        assert result["source.ip"] == "1.2.3.4"
        assert result["user.name"] == "alice"
        assert result["file.hash.sha256"] == "a" * 64
        assert result["process.name"] == "cmd.exe"


# ---------------------------------------------------------------------------
# AlertEntity persistence (via _save_alert_entities helper path)
# ---------------------------------------------------------------------------

class TestAlertEntityPersistence:
    def test_entities_written_on_ingest(self, acme):
        alert = _make_alert(acme)
        from alerts.views import _save_alert_entities
        _save_alert_entities(alert, acme, {"host.name": "web-01", "user.name": "CORP\\alice"})

        ents = AlertEntity.objects.filter(alert=alert).order_by("entity_type")
        assert ents.count() == 2
        types = {e.entity_type: e.value for e in ents}
        assert types["host.name"] == "web-01"
        assert types["user.name"] == "alice"

    def test_entities_carry_correct_org(self, acme):
        alert = _make_alert(acme)
        from alerts.views import _save_alert_entities
        _save_alert_entities(alert, acme, {"source.ip": "10.0.0.5"})

        ent = AlertEntity.objects.get(alert=alert)
        assert ent.organization_id == acme.pk

    def test_no_entities_when_envelope_absent(self, acme):
        alert = _make_alert(acme)
        from alerts.views import _save_alert_entities
        _save_alert_entities(alert, acme, None)

        assert AlertEntity.objects.filter(alert=alert).count() == 0

    def test_alert_without_envelope_succeeds(self, acme):
        """Alerts ingested without an envelope still produce an Alert row."""
        alert = _make_alert(acme)
        assert alert.pk is not None
        assert AlertEntity.objects.filter(alert=alert).count() == 0

    def test_query_by_org_entity_type_value(self, acme):
        alert = _make_alert(acme)
        from alerts.views import _save_alert_entities
        _save_alert_entities(alert, acme, {"user.name": "alice@corp.example"})

        qs = AlertEntity.objects.filter(
            organization=acme, entity_type="user.name", value="alice"
        )
        assert qs.count() == 1
        assert qs.first().alert_id == alert.pk

    def test_cross_source_same_entity_joins(self, acme):
        """Two alerts with user formats that canonicalise to the same value are queryable together."""
        a1 = _make_alert(acme)
        a2 = _make_alert(acme)
        from alerts.views import _save_alert_entities
        _save_alert_entities(a1, acme, {"user.name": "CORP\\alice"})
        _save_alert_entities(a2, acme, {"user.name": "alice@corp.example.com"})

        qs = AlertEntity.objects.filter(
            organization=acme, entity_type="user.name", value="alice"
        )
        assert qs.count() == 2
        alert_ids = set(qs.values_list("alert_id", flat=True))
        assert alert_ids == {a1.pk, a2.pk}

    def test_unknown_ecs_keys_silently_ignored(self, acme):
        alert = _make_alert(acme)
        from alerts.views import _save_alert_entities
        _save_alert_entities(alert, acme, {"host.name": "web-01", "host.group": "dmz"})

        ents = AlertEntity.objects.filter(alert=alert)
        assert ents.count() == 1
        assert ents.first().entity_type == "host.name"
