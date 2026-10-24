import json
from fastapi.testclient import TestClient
from main import app
from db.session import get_db
from models.users import User, UserActivity, UserConsent

client = TestClient(app)


def test_anonymization_workflow_and_referential_integrity():
    """Перевірка анонімізації: PII очищено, зв'язки збережені, IP замінено на 0.0.0.0."""
    anon_res = client.post("/api/v1/users/1/anonymize", headers={"x-user-id": "1"})
    assert anon_res.status_code == 200
    assert anon_res.json()["status"] == "success"

    # Перевірка в реальній БД
    db = next(get_db())
    user = db.query(User).filter(User.id == 1).first()

    assert user.email == "deleted_user_1@anon.local"
    assert user.username == "deleted_user_1"
    assert user.phone is None
    assert user.hashed_password == "[REDACTED_DELETED]"
    assert user.is_anonymized is True

    # Зв'язки цілі, IP в історії очищено
    activities = db.query(UserActivity).filter(UserActivity.user_id == 1).all()
    for act in activities:
        payload = json.loads(act.details) if isinstance(act.details, str) else act.details
        if isinstance(payload, dict) and "ip" in payload:
            assert payload["ip"] == "0.0.0.0"

    consents = db.query(UserConsent).filter(UserConsent.user_id == 1).all()
    assert all(c.is_granted is False for c in consents)
    db.close()


def test_anonymization_idempotence():
    """Перевірка ідемпотентності: повторний виклик повертає 200 без помилок."""
    client.post("/api/v1/users/1/anonymize", headers={"x-user-id": "1"})
    repeat_res = client.post("/api/v1/users/1/anonymize", headers={"x-user-id": "1"})

    assert repeat_res.status_code == 200
    assert "already anonymized" in repeat_res.json()["message"]


def test_anonymization_idor_forbidden():
    """Негативний тест: неможливо анонімізувати чужий профіль."""
    response = client.post("/api/v1/users/1/anonymize", headers={"x-user-id": "2"})
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]