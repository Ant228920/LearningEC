"""Поведінкові тести експортерів (Лаб. №8, Завд. 3). Однакові на всіх станах дизайну.

Створення об'єктів іде через фабрики make_*_exporter: при переході від наслідування до
композиції змінюється лише спосіб складання, а не публічна поведінка.
"""
import json
from datetime import datetime, timezone

import pytest

from services.privacy.contracts import ActivityRecord, ConsentRecord, UserNotFound, UserRecord
from services.privacy.exporters import make_base_exporter, make_gdpr_exporter, make_json_exporter

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


class FakeUsers:
    def __init__(self, user):
        self.user = user

    def get(self, user_id):
        return self.user

    def list_activities(self, user_id):
        return [ActivityRecord("LOGIN", NOW, {"ip": "1.2.3.4"})]


class FakeConsents:
    def list_for(self, user_id):
        return [ConsentRecord(user_id, "MARKETING_EMAIL", True, "v1.0", NOW)]


def user(anonymized=False, phone="+380501234567"):
    return UserRecord(user_id=7, email="a@b.c", username="olena", phone=phone, is_anonymized=anonymized)


def build(factory, subject=None):
    return factory(FakeUsers(subject if subject is not None else user()), FakeConsents())


# --------------------------------------------------------------------------- BaseExporter
def test_base_exports_plain_dict():
    result = build(make_base_exporter).export(7)
    assert set(result) == {"profile", "activities", "consents"}
    assert result["profile"]["email"] == "a@b.c"
    assert result["activities"][0]["details"] == {"ip": "1.2.3.4"}


def test_base_format_descriptors():
    exporter = build(make_base_exporter)
    assert exporter.content_type() == "application/octet-stream"
    assert exporter.file_name(7) == "export_7.bin"


# --------------------------------------------------------------------------- JsonExporter
def test_json_exports_json_string_with_format_marker():
    exporter = build(make_json_exporter)
    data = json.loads(exporter.export(7))
    assert data["format"] == "json"
    assert data["profile"]["phone"] == "+380501234567"
    assert exporter.to_json(7) == exporter.export(7)
    assert exporter.parse(exporter.export(7)) == data


def test_json_format_descriptors():
    exporter = build(make_json_exporter)
    assert exporter.content_type() == "application/json"
    assert exporter.file_name(7) == "export_7.json"


# --------------------------------------------------------------------------- GdprJsonExporter
def test_gdpr_envelope_and_masked_phone():
    exporter = build(make_gdpr_exporter)
    data = json.loads(exporter.export(7))
    assert data["export_metadata"] == {"schema_version": "1.0", "legal_basis": "GDPR Article 15 (Right of Access)"}
    assert data["profile"]["phone"] == "***"
    assert data["activity_history"][0]["action"] == "LOGIN"
    assert data["consents"][0]["is_granted"] is True
    assert "format" not in data


def test_gdpr_output_is_sorted_and_not_ascii_escaped():
    text = build(make_gdpr_exporter).export(7)
    assert text.index('"activity_history"') < text.index('"consents"') < text.index('"export_metadata"')


def test_gdpr_without_phone_stays_none():
    data = json.loads(build(make_gdpr_exporter, user(phone=None)).export(7))
    assert data["profile"]["phone"] is None


def test_gdpr_format_descriptors():
    exporter = build(make_gdpr_exporter)
    assert exporter.content_type() == "application/gdpr+json"
    assert exporter.file_name(7) == "gdpr_export_7.json"
    assert (exporter.schema_version(), exporter.legal_basis()) == ("1.0", "GDPR Article 15 (Right of Access)")


def test_gdpr_rejects_anonymized_subject():
    with pytest.raises(UserNotFound):
        build(make_gdpr_exporter, user(anonymized=True)).export(7)


def test_every_exporter_rejects_unknown_subject():
    users = FakeUsers(None)
    for factory in (make_base_exporter, make_json_exporter, make_gdpr_exporter):
        with pytest.raises(UserNotFound):
            factory(users, FakeConsents()).export(7)