"""Поведінкові тести Privacy API (GDPR) без реального Postgres.

Призначення в лабораторній №8: «страховка» під час рефакторингу. Ті самі тести
мають проходити на кожному стані дизайну (God Object -> декомпозиція), доки
зміна поведінки не потрібна. Окрема in-memory SQLite база + dependency override
замість `main.app`, тому тести не залежать від Docker / .env.
"""
import json
import os

for _key, _value in {
    "DB_USER": "test", "DB_PASSWORD": "test", "DB_HOST": "localhost", "DB_PORT": "5432", "DB_NAME": "test",
}.items():
    os.environ.setdefault(_key, _value)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.v1.endpoints.privacy import privacy_router
from db.session import Base, get_db
from models.users import User, UserActivity, UserConsent

def stored_flags(db, user_id):
    """is_granted читаємо через колонку таблиці, а не через ORM-атрибут: тест не залежить від його назви."""
    table = UserConsent.__table__
    rows = db.execute(table.select().where(table.c.user_id == user_id)).all()
    return [row.is_granted for row in rows]


HEADERS_1 = {"x-user-id": "1"}
HEADERS_2 = {"x-user-id": "2"}
CAMPAIGN = {"campaign_name": "Autumn Promo", "message": "Discounts inside"}


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    with factory() as seed:
        seed.add_all([
            User(id=1, email="olena@example.com", username="olena", phone="+380501234567",
                 hashed_password="hash1", internal_antifraud_score="0.91"),
            User(id=2, email="ivan@example.com", username="ivan", phone=None, hashed_password="hash2"),
            UserActivity(user_id=1, action="LOGIN", details=json.dumps({"ip": "192.168.1.10", "ua": "pytest"})),
            UserActivity(user_id=1, action="VIEW", details="not-a-json"),
        ])
        seed.execute(UserConsent.__table__.insert().values(
            user_id=1, purpose="OPTIONAL_ANALYTICS", is_granted=True, policy_version="v1.0"))
        seed.commit()

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(privacy_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app), factory
    engine.dispose()


# --------------------------------------------------------------------------- Right of Access
def test_export_returns_profile_and_metadata(env):
    client, _ = env
    res = client.get("/api/v1/users/1/personal-data", headers=HEADERS_1)
    assert res.status_code == 200
    data = res.json()
    assert data["subject_id"] == 1
    assert data["profile"]["email"] == "olena@example.com"
    assert data["export_metadata"]["legal_basis"].startswith("GDPR Article 15")


def test_export_hides_internal_fields(env):
    client, _ = env
    profile = client.get("/api/v1/users/1/personal-data", headers=HEADERS_1).json()["profile"]
    assert not {"hashed_password", "password", "internal_antifraud_score"} & set(profile)


def test_export_includes_activities_and_consents(env):
    client, _ = env
    data = client.get("/api/v1/users/1/personal-data", headers=HEADERS_1).json()
    assert {a["action"] for a in data["activity_history"]} == {"LOGIN", "VIEW"}
    assert data["consents"][0]["purpose"] == "OPTIONAL_ANALYTICS"
    raw = [a for a in data["activity_history"] if a["action"] == "VIEW"][0]
    assert raw["details"] == {"raw": "not-a-json"}


def test_export_idor_forbidden(env):
    client, _ = env
    res = client.get("/api/v1/users/1/personal-data", headers=HEADERS_2)
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]


def test_export_unknown_user_not_found(env):
    client, _ = env
    res = client.get("/api/v1/users/999/personal-data", headers={"x-user-id": "999"})
    assert res.status_code == 404
    assert "User not found" in res.json()["detail"]


# --------------------------------------------------------------------------- Right to Erasure
def anonymize_user_1(env):
    client, factory = env
    res = client.post("/api/v1/users/1/anonymize", headers=HEADERS_1)
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    return factory


def test_anonymize_clears_user_pii(env):
    with anonymize_user_1(env)() as db:
        user = db.query(User).filter(User.id == 1).one()
        assert user.email == "deleted_user_1@anon.local"
        assert user.username == "deleted_user_1"
        assert user.phone is None
        assert user.hashed_password == "[REDACTED_DELETED]"
        assert user.internal_antifraud_score is None
        assert user.is_anonymized is True


def test_anonymize_masks_ip_and_keeps_activity_history(env):
    with anonymize_user_1(env)() as db:
        login = db.query(UserActivity).filter(UserActivity.action == "LOGIN").one()
        assert json.loads(login.details)["ip"] == "0.0.0.0"
        assert db.query(UserActivity).filter(UserActivity.user_id == 1).count() == 2


def test_anonymize_revokes_consents(env):
    with anonymize_user_1(env)() as db:
        assert stored_flags(db, user_id=1) == [False]


def test_anonymize_is_idempotent(env):
    client, _ = env
    client.post("/api/v1/users/1/anonymize", headers=HEADERS_1)
    again = client.post("/api/v1/users/1/anonymize", headers=HEADERS_1)
    assert again.status_code == 200
    assert "already anonymized" in again.json()["message"]


def test_anonymize_idor_forbidden(env):
    client, _ = env
    res = client.post("/api/v1/users/1/anonymize", headers=HEADERS_2)
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]


# --------------------------------------------------------------------------- Consent engine + Policy Gate
def post_consent(client, action, version):
    return client.post(f"/api/v1/users/2/consents/{action}",
                       json={"purpose": "MARKETING_EMAIL", "policy_version": version}, headers=HEADERS_2)


def test_marketing_denied_without_consent_then_allowed_after_grant(env):
    client, _ = env
    url = "/api/v1/users/2/actions/send-marketing"
    assert client.post(url, json=CAMPAIGN, headers=HEADERS_2).status_code == 403

    grant = post_consent(client, "grant", "v2.0")
    assert (grant.status_code, grant.json()["is_granted"], grant.json()["policy_version"]) == (200, True, "v2.0")

    allow = client.post(url, json=CAMPAIGN, headers=HEADERS_2)
    assert allow.status_code == 200
    assert allow.json() == {"status": "ALLOW", "action": "Marketing email sent successfully",
                            "campaign": "Autumn Promo"}


def test_revoke_denies_marketing_again_and_keeps_policy_version(env):
    client, _ = env
    url = "/api/v1/users/2/actions/send-marketing"
    post_consent(client, "grant", "v2.0")

    revoke = post_consent(client, "revoke", "v3.0")
    assert revoke.json()["is_granted"] is False
    assert revoke.json()["policy_version"] == "v2.0"  # revoke не перезаписує версію політики

    denied = client.post(url, json=CAMPAIGN, headers=HEADERS_2)
    assert denied.status_code == 403
    assert "Policy Gate DENY" in denied.json()["detail"]


def test_consent_purpose_isolation(env):
    client, _ = env
    client.post("/api/v1/users/2/consents/grant",
                json={"purpose": "OPTIONAL_ANALYTICS"}, headers=HEADERS_2)
    res = client.post("/api/v1/users/2/actions/send-marketing", json=CAMPAIGN, headers=HEADERS_2)
    assert res.status_code == 403
    assert "Missing or revoked consent for MARKETING_EMAIL" in res.json()["detail"]


def test_revoke_without_prior_record_creates_denied_consent(env):
    client, factory = env
    res = client.post("/api/v1/users/2/consents/revoke",
                      json={"purpose": "MARKETING_EMAIL", "policy_version": "v1.5"}, headers=HEADERS_2)
    assert res.status_code == 200
    assert res.json()["is_granted"] is False
    assert res.json()["policy_version"] == "v1.5"
    with factory() as db:
        assert db.query(UserConsent).filter(UserConsent.user_id == 2).count() == 1


@pytest.mark.parametrize("path, payload", [
    ("/api/v1/users/1/consents/grant", {"purpose": "MARKETING_EMAIL"}),
    ("/api/v1/users/1/consents/revoke", {"purpose": "MARKETING_EMAIL"}),
    ("/api/v1/users/1/actions/send-marketing", CAMPAIGN),
])
def test_consent_endpoints_reject_foreign_actor(env, path, payload):
    client, _ = env
    res = client.post(path, json=payload, headers=HEADERS_2)
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]