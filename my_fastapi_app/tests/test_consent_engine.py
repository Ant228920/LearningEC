from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_consent_lifecycle_grant_allow_revoke_deny():
    """Повний сценарій: DENY -> GRANT -> ALLOW -> REVOKE -> DENY."""
    user_id = 2
    headers = {"x-user-id": str(user_id)}
    campaign_payload = {"campaign_name": "Autumn Promo", "message": "Discounts inside"}

    # 1. DENY
    res_deny_init = client.post(f"/api/v1/users/{user_id}/actions/send-marketing", json=campaign_payload, headers=headers)
    assert res_deny_init.status_code == 403
    assert "Policy Gate DENY" in res_deny_init.json()["detail"]

    # 2. GRANT
    res_grant = client.post(
        f"/api/v1/users/{user_id}/consents/grant",
        json={"purpose": "MARKETING_EMAIL", "policy_version": "v1.0"},
        headers=headers,
    )
    assert res_grant.status_code == 200
    assert res_grant.json()["is_granted"] is True

    # 3. ALLOW
    res_allow = client.post(f"/api/v1/users/{user_id}/actions/send-marketing", json=campaign_payload, headers=headers)
    assert res_allow.status_code == 200
    assert res_allow.json()["status"] == "ALLOW"

    # 4. REVOKE
    res_revoke = client.post(
        f"/api/v1/users/{user_id}/consents/revoke",
        json={"purpose": "MARKETING_EMAIL", "policy_version": "v1.0"},
        headers=headers,
    )
    assert res_revoke.status_code == 200
    assert res_revoke.json()["is_granted"] is False

    # 5. DENY
    res_deny_final = client.post(f"/api/v1/users/{user_id}/actions/send-marketing", json=campaign_payload, headers=headers)
    assert res_deny_final.status_code == 403
    assert "Policy Gate DENY" in res_deny_final.json()["detail"]


def test_consent_purpose_isolation():
    """Ізоляція: згода на OPTIONAL_ANALYTICS не дає доступу до MARKETING_EMAIL."""
    user_id = 2
    headers = {"x-user-id": str(user_id)}

    client.post(
        f"/api/v1/users/{user_id}/consents/grant",
        json={"purpose": "OPTIONAL_ANALYTICS", "policy_version": "v1.0"},
        headers=headers,
    )

    response = client.post(
        f"/api/v1/users/{user_id}/actions/send-marketing",
        json={"campaign_name": "Promo", "message": "Text"},
        headers=headers,
    )
    assert response.status_code == 403
    assert "Missing or revoked consent for MARKETING_EMAIL" in response.json()["detail"]