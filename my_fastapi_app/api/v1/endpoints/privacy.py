import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from models.users import User, UserActivity, UserConsent
from schemas.privacy import (
    AnonymizeResponse,
    ConsentActionResponse,
    ConsentPurpose,
    ConsentUpdateRequest,
    MarketingCampaignRequest,
    PersonalDataExportResponse,
    UserActivityExport,
    UserProfileExport,
    ConsentExport,
)

logger = logging.getLogger("api")

privacy_router = APIRouter(prefix="/users", tags=["Privacy & GDPR"])


# ==========================================
# Policy Gate Component (Завдання 4)
# ==========================================

class ConsentPolicyGate:
    """Перевірка активної згоди перед виконанням бізнес-дії."""

    @staticmethod
    def check_consent(db: Session, user_id: int, purpose: ConsentPurpose) -> bool:
        consent = (
            db.query(UserConsent)
            .filter(
                UserConsent.user_id == user_id,
                UserConsent.purpose == purpose.value,
                UserConsent.is_granted.is_(True),
            )
            .first()
        )
        return consent is not None


# ==========================================
# Завдання 2: Personal Data Export (Article 15)
# ==========================================

@privacy_router.get(
    "/{user_id}/personal-data",
    response_model=PersonalDataExportResponse,
    status_code=status.HTTP_200_OK,
    summary="Export User Personal Data (Right of Access)",
)
def export_user_personal_data(
    user_id: int,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    db: Session = Depends(get_db),
):
    # 1. Захист від IDOR та Enumeration
    if user_id != x_user_id:
        logger.warning("Access denied: Actor %s tried to export data of User %s", x_user_id, user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You are not authorized to export another user's data.",
        )

    # 2. Отримання даних із БД
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    db_activities = db.query(UserActivity).filter(UserActivity.user_id == user_id).all()
    db_consents = db.query(UserConsent).filter(UserConsent.user_id == user_id).all()

    # 3. Мінімізація: віддаються тільки безпечні поля
    profile = UserProfileExport(
        user_id=user.id,
        email=user.email,
        username=user.username,
        phone=user.phone,
    )

    activities = []
    for act in db_activities:
        parsed_details = {}
        if act.details:
            try:
                parsed_details = json.loads(act.details) if isinstance(act.details, str) else act.details
            except Exception:
                parsed_details = {"raw": str(act.details)}
        activities.append(
            UserActivityExport(
                action=act.action,
                timestamp=act.timestamp,
                details=parsed_details,
            )
        )

    consents = [
        ConsentExport(
            purpose=c.purpose,
            is_granted=c.is_granted,
            policy_version=c.policy_version,
            updated_at=c.updated_at,
        )
        for c in db_consents
    ]

    logger.info("Personal data export generated successfully for subject_id=%s", user_id)

    return PersonalDataExportResponse(
        export_metadata={
            "schema_version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "legal_basis": "GDPR Article 15 (Right of Access)",
        },
        subject_id=user_id,
        profile=profile,
        activity_history=activities,
        consents=consents,
    )


# ==========================================
# Завдання 3: Right to Erasure / Anonymization (Article 17)
# ==========================================

@privacy_router.post(
    "/{user_id}/anonymize",
    response_model=AnonymizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Anonymize User Data (Right to Erasure)",
)
def anonymize_user_data(
    user_id: int,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    db: Session = Depends(get_db),
):
    if user_id != x_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You cannot anonymize another user's profile.",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    # Ідемпотентність
    if user.is_anonymized:
        return AnonymizeResponse(
            status="success",
            message="User profile is already anonymized (idempotent response).",
            user_id=user_id,
            anonymized_at=datetime.now(timezone.utc).isoformat(),
        )

    try:
        # Анонімізація прямих ідентифікаторів у таблиці users
        user.email = f"deleted_user_{user_id}@anon.local"
        user.username = f"deleted_user_{user_id}"
        user.phone = None
        user.hashed_password = "[REDACTED_DELETED]"
        user.internal_antifraud_score = None
        user.is_anonymized = True

        # Знеособлення непрямих ідентифікаторів (IP) в user_activities
        activities = db.query(UserActivity).filter(UserActivity.user_id == user_id).all()
        for act in activities:
            if act.details:
                try:
                    payload = json.loads(act.details) if isinstance(act.details, str) else act.details
                    if isinstance(payload, dict) and "ip" in payload:
                        payload["ip"] = "0.0.0.0"
                    act.details = json.dumps(payload)
                except Exception:
                    pass

        # Деактивація активних згод
        consents = db.query(UserConsent).filter(UserConsent.user_id == user_id).all()
        for c in consents:
            c.is_granted = False
            c.updated_at = datetime.now(timezone.utc)

        db.commit()

        logger.info("Audit: User subject_id=%s was irreversibly anonymized by actor_id=%s", user_id, x_user_id)

    except Exception as e:
        db.rollback()
        logger.error("Anonymization failed for user %s: %s", user_id, str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction failed during anonymization workflow.",
        )

    return AnonymizeResponse(
        status="success",
        message="User personal data has been irreversibly anonymized.",
        user_id=user_id,
        anonymized_at=datetime.now(timezone.utc).isoformat(),
    )


# ==========================================
# Завдання 4: Consent Management Engine (Article 7)
# ==========================================

@privacy_router.post("/{user_id}/consents/grant", response_model=ConsentActionResponse)
def grant_consent(
    user_id: int,
    req: ConsentUpdateRequest,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    db: Session = Depends(get_db),
):
    if user_id != x_user_id:
        raise HTTPException(status_code=403, detail="Access denied: Cannot manage consent for another user.")

    consent = (
        db.query(UserConsent)
        .filter(UserConsent.user_id == user_id, UserConsent.purpose == req.purpose.value)
        .first()
    )
    now_utc = datetime.now(timezone.utc)

    if consent:
        consent.is_granted = True
        consent.policy_version = req.policy_version
        consent.updated_at = now_utc
    else:
        consent = UserConsent(
            user_id=user_id,
            purpose=req.purpose.value,
            is_granted=True,
            policy_version=req.policy_version,
            updated_at=now_utc,
        )
        db.add(consent)

    db.commit()
    db.refresh(consent)

    logger.info("Consent granted: user_id=%s purpose=%s version=%s", user_id, req.purpose.value, req.policy_version)

    return ConsentActionResponse(
        user_id=user_id,
        purpose=req.purpose,
        is_granted=True,
        policy_version=consent.policy_version,
        updated_at=consent.updated_at.isoformat(),
    )


@privacy_router.post("/{user_id}/consents/revoke", response_model=ConsentActionResponse)
def revoke_consent(
    user_id: int,
    req: ConsentUpdateRequest,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    db: Session = Depends(get_db),
):
    if user_id != x_user_id:
        raise HTTPException(status_code=403, detail="Access denied: Cannot manage consent for another user.")

    consent = (
        db.query(UserConsent)
        .filter(UserConsent.user_id == user_id, UserConsent.purpose == req.purpose.value)
        .first()
    )
    now_utc = datetime.now(timezone.utc)

    if consent:
        consent.is_granted = False
        consent.updated_at = now_utc
    else:
        consent = UserConsent(
            user_id=user_id,
            purpose=req.purpose.value,
            is_granted=False,
            policy_version=req.policy_version,
            updated_at=now_utc,
        )
        db.add(consent)

    db.commit()
    db.refresh(consent)

    logger.info("Consent revoked: user_id=%s purpose=%s", user_id, req.purpose.value)

    return ConsentActionResponse(
        user_id=user_id,
        purpose=req.purpose,
        is_granted=False,
        policy_version=consent.policy_version,
        updated_at=consent.updated_at.isoformat(),
    )


@privacy_router.post("/{user_id}/actions/send-marketing")
def execute_marketing_action(
    user_id: int,
    body: MarketingCampaignRequest,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    db: Session = Depends(get_db),
):
    if user_id != x_user_id:
        raise HTTPException(status_code=403, detail="Access denied.")

    # Перевірка Policy Gate перед виконанням операції
    has_consent = ConsentPolicyGate.check_consent(db, user_id, ConsentPurpose.MARKETING_EMAIL)
    if not has_consent:
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