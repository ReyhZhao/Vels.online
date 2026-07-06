"""Partner intake slice 2 (#670): the pure field-mapping engine. No DB."""

from types import SimpleNamespace

import pytest

from inbound_mail.dataclasses import NormalisedMessage
from partners.mapping import extract_external_reference, map_email_to_incident_fields


def conn(field_mappings=None, external_reference_regex=""):
    return SimpleNamespace(
        field_mappings=field_mappings or {},
        external_reference_regex=external_reference_regex,
    )


def msg(subject="Detected malware on host", body_text="Severity: P1\nTLP: AMBER"):
    return NormalisedMessage(
        from_address="soc@peer.example", to_address="soc@vels.online", reply_to=None,
        subject=subject, body_text=body_text, body_html="",
    )


# ── per-field precedence ─────────────────────────────────────────────────────────


def test_regex_hit_then_value_map_translation():
    c = conn({"severity": {"regex": r"Severity:\s*(\w+)", "value_map": {"P1": "critical"}, "default": "medium"}})
    assert map_email_to_incident_fields(c, msg())["severity"] == "critical"


def test_value_map_is_case_insensitive():
    c = conn({"tlp": {"regex": r"TLP:\s*(\w+)", "value_map": {"amber": "amber"}, "default": "green"}})
    assert map_email_to_incident_fields(c, msg())["tlp"] == "amber"


def test_regex_hit_normalises_and_enum_matches():
    c = conn({"severity": {"regex": r"Severity:\s*(\w+)", "default": "medium"}})
    assert map_email_to_incident_fields(c, msg(body_text="Severity: HIGH"))["severity"] == "high"


def test_capture_not_a_valid_enum_falls_back_to_default():
    c = conn({"severity": {"regex": r"Severity:\s*(\w+)", "default": "low"}})
    assert map_email_to_incident_fields(c, msg(body_text="Severity: bogus"))["severity"] == "low"


def test_empty_regex_uses_default():
    c = conn({"severity": {"regex": "", "default": "high"}})
    assert map_email_to_incident_fields(c, msg())["severity"] == "high"


def test_no_default_and_no_match_uses_system_fallback():
    c = conn({"severity": {"regex": r"Sev=(\w+)"}})  # never matches
    out = map_email_to_incident_fields(c, msg())
    assert out["severity"] == "medium"
    assert out["tlp"] == "amber"


def test_malformed_regex_is_treated_as_no_match():
    c = conn({"severity": {"regex": "[unclosed", "default": "low"}})
    assert map_email_to_incident_fields(c, msg())["severity"] == "low"


def test_title_defaults_to_subject_and_description_to_body():
    out = map_email_to_incident_fields(conn(), msg(subject="Peer detection X", body_text="details here"))
    assert out["title"] == "Peer detection X"
    assert out["description"] == "details here"


def test_title_free_text_capture_used_directly():
    c = conn({"title": {"regex": r"Alert:\s*(.+)"}})
    assert map_email_to_incident_fields(c, msg(subject="Alert: brute force"))["title"] == "brute force"


# ── external reference ───────────────────────────────────────────────────────────


def test_external_reference_captured_from_subject():
    c = conn(external_reference_regex=r"\[(INC-[\d-]+)\]")
    assert extract_external_reference(c, msg(subject="Update [INC-2024-0142] follow-up")) == "INC-2024-0142"


def test_external_reference_empty_when_no_regex():
    assert extract_external_reference(conn(), msg()) == ""


def test_external_reference_empty_when_no_match():
    c = conn(external_reference_regex=r"\[(INC-[\d-]+)\]")
    assert extract_external_reference(c, msg(subject="no ref here")) == ""
