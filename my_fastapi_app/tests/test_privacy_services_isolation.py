"""Ізольовані unit-тести сервісів на фейкових портах: без БД, без FastAPI, без SQLAlchemy.

Доказ Dependency Inversion (Лаб. №8, Завд. 2): після декомпозиції бізнес-логіку можна
запустити, підклавши будь-яку реалізацію UserStore / ConsentStore / UnitOfWork.
"""
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from schemas.privacy import ConsentPurpose
from services.privacy.anonymization import AnonymizationService
from services.privacy.consent import ConsentPolicyGate, ConsentService
from services.privacy.contracts import (
    ActivityRecord,
    AnonymizationFailed,
    ConsentRecord,
    UserNotFound,
    UserRecord,
)
from services.privacy.data_export import DataExportService

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)
MARKETING = ConsentPurpose.MARKETING_EMAIL


class FakeUow:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeConsents:
    def __init__(self, *records):
        self.items = {(r.user_id, r.purpose): r for r in records}
        self.revoked_for = []
        self.fail_on_revoke = False

    def find(self, user_id, purpose):
        return self.items.get((user_id, purpose))

    def list_for(self, user_id):
        return [r for (uid, _), r in self.items.items() if uid == user_id]

    def save(self, record):
        self.items[(record.user_id, record.purpose)] = record
        return record

    def revoke_all(self, user_id, at):
        if self.fail_on_revoke:
            raise RuntimeError("db down")
        self.revoked_for.append(user_id)


class FakeUsers:
    def __init__(self, user=None):
        self.user = user
        self.calls = []

    def get(self, user_id):
        return self.user

    def list_activities(self, user_id):
        return [ActivityRecord("LOGIN", NOW, {"ip": "1.2.3.4"})]

    def erase_identity(self, user_id, email, username):
        self.calls.append(("erase", email, username))

    def mask_activity_ips(self, user_id, mask):
        self.calls.append(("mask", mask))


def make_user(anonymized=False):
    return UserRecord(user_id=7, email="a@b.c", username="a", phone=None, is_anonymized=anonymized)


# --------------------------------------------------------------------------- ConsentService
def test_grant_saves_granted_record_and_commits_once():
    consents, uow = FakeConsents(), FakeUow()
    saved = ConsentService(consents, uow).grant(7, MARKETING, "v2.0")
    assert (saved.is_granted, saved.policy_version) == (True, "v2.0")
    assert uow.commits == 1


def test_revoke_keeps_existing_policy_version():
    existing = ConsentRecord(7, "MARKETING_EMAIL", True, "v1.0", NOW)
    saved = ConsentService(FakeConsents(existing), FakeUow()).revoke(7, MARKETING, "v9.9")
    assert (saved.is_granted, saved.policy_version) == (False, "v1.0")


def test_revoke_without_record_uses_requested_version():
    saved = ConsentService(FakeConsents(), FakeUow()).revoke(7, MARKETING, "v1.5")
    assert (saved.is_granted, saved.policy_version) == (False, "v1.5")


# --------------------------------------------------------------------------- ConsentPolicyGate
def test_gate_allows_only_active_consent_for_the_same_purpose():
    granted = ConsentRecord(7, "MARKETING_EMAIL", True, "v1.0", NOW)
    assert ConsentPolicyGate(FakeConsents(granted)).check_consent(7, MARKETING) is True
    assert ConsentPolicyGate(FakeConsents(replace(granted, is_granted=False))).check_consent(7, MARKETING) is False
    assert ConsentPolicyGate(FakeConsents(granted)).check_consent(7, ConsentPurpose.OPTIONAL_ANALYTICS) is False
    assert ConsentPolicyGate(FakeConsents()).check_consent(7, MARKETING) is False


# --------------------------------------------------------------------------- AnonymizationService
def test_anonymize_erases_masks_revokes_and_commits():
    users, consents, uow = FakeUsers(make_user()), FakeConsents(), FakeUow()
    res = AnonymizationService(users, consents, uow).anonymize(7, actor_id=7)
    assert res.status == "success"
    assert users.calls == [("erase", "deleted_user_7@anon.local", "deleted_user_7"), ("mask", "0.0.0.0")]
    assert consents.revoked_for == [7]
    assert (uow.commits, uow.rollbacks) == (1, 0)


def test_anonymize_is_idempotent_and_touches_nothing():
    users, uow = FakeUsers(make_user(anonymized=True)), FakeUow()
    res = AnonymizationService(users, FakeConsents(), uow).anonymize(7, actor_id=7)
    assert "already anonymized" in res.message
    assert users.calls == [] and uow.commits == 0


def test_anonymize_rolls_back_on_failure():
    consents, uow = FakeConsents(), FakeUow()
    consents.fail_on_revoke = True
    with pytest.raises(AnonymizationFailed):
        AnonymizationService(FakeUsers(make_user()), consents, uow).anonymize(7, actor_id=7)
    assert (uow.commits, uow.rollbacks) == (0, 1)


def test_anonymize_unknown_user():
    with pytest.raises(UserNotFound):
        AnonymizationService(FakeUsers(None), FakeConsents(), FakeUow()).anonymize(7, actor_id=7)


# --------------------------------------------------------------------------- DataExportService
def test_export_assembles_bundle_from_ports():
    consent = ConsentRecord(7, "MARKETING_EMAIL", True, "v1.0", NOW)
    res = DataExportService(FakeUsers(make_user()), FakeConsents(consent)).export(7)
    assert res.subject_id == 7 and res.profile.email == "a@b.c"
    assert res.activity_history[0].details == {"ip": "1.2.3.4"}
    assert res.consents[0].is_granted is True


def test_export_unknown_user():
    with pytest.raises(UserNotFound):
        DataExportService(FakeUsers(None), FakeConsents()).export(7)
