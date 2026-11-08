from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_export_personal_data_success_and_minimization():
    """Позитивний тест: успішний експорт власних даних та перевірка відсутності паролів."""
    response = client.get("/api/v1/users/1/personal-data", headers={"x-user-id": "1"})
    assert response.status_code == 200
    data = response.json()

    assert data["subject_id"] == 1
    assert "profile" in data
    assert "email" in data["profile"]

    # Мінімізація: заборонені поля відсутні у відповіді
    profile_keys = data["profile"].keys()
    assert "hashed_password" not in profile_keys
    assert "password" not in profile_keys
    assert "internal_antifraud_score" not in profile_keys


def test_export_personal_data_idor_forbidden():
    """Негативний тест (IDOR): спроба експортувати чужі дані повертає 403 Forbidden."""
    response = client.get("/api/v1/users/1/personal-data", headers={"x-user-id": "2"})
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]


def test_export_personal_data_user_not_found():
    """Негативний тест: спроба експорту неіснуючого профілю від свого імені."""
    response = client.get("/api/v1/users/999/personal-data", headers={"x-user-id": "999"})
    assert response.status_code == 404
    assert "User not found" in response.json()["detail"]