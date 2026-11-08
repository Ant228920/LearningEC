"""Маршрути Consent Engine та Policy Gate."""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status

from api.v1.privacy_deps import get_consent_service, get_policy_gate, require_subject
from schemas.privacy import (
    ConsentActionResponse,
    ConsentPurpose,
    ConsentUpdateRequest,
    MarketingCampaignRequest,
)
from services.privacy.consent import ConsentPolicyGate, ConsentService
from services.privacy.contracts import ConsentRecord

logger = logging.getLogger("api")

consent_router = APIRouter()


def to_consent_response(record: ConsentRecord) -> ConsentActionResponse:
    return ConsentActionResponse(
        user_id=record.user_id,
        purpose=ConsentPurpose(record.purpose),
        is_granted=record.is_granted,
        policy_version=record.policy_version,
        updated_at=record.updated_at.isoformat(),
    )


@consent_router.post("/{user_id}/consents/grant", response_model=ConsentActionResponse)
def grant_consent(
    user_id: int,
    req: ConsentUpdateRequest,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    service: ConsentService = Depends(get_consent_service),
):
    require_subject(user_id, x_user_id, "Access denied: Cannot manage consent for another user.")
    return to_consent_response(service.grant(user_id, req.purpose, req.policy_version))


@consent_router.post("/{user_id}/consents/revoke", response_model=ConsentActionResponse)
def revoke_consent(
    user_id: int,
    req: ConsentUpdateRequest,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    service: ConsentService = Depends(get_consent_service),
):
    require_subject(user_id, x_user_id, "Access denied: Cannot manage consent for another user.")
    return to_consent_response(service.revoke(user_id, req.purpose, req.policy_version))


@consent_router.post("/{user_id}/actions/send-marketing")
def execute_marketing_action(
    user_id: int,
    body: MarketingCampaignRequest,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    gate: ConsentPolicyGate = Depends(get_policy_gate),
):
    require_subject(user_id, x_user_id, "Access denied.")
    if not gate.check_consent(user_id, ConsentPurpose.MARKETING_EMAIL):
        logger.warning("Policy Gate DENY: user_id=%s has no active MARKETING_EMAIL consent", user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Policy Gate DENY: Missing or revoked consent for MARKETING_EMAIL.",
        )
    logger.info("Policy Gate ALLOW: Marketing email sent to user_id=%s", user_id)
    return {
        "status": "ALLOW",
        "action": "Marketing email sent successfully",
        "campaign": body.campaign_name,
    }
