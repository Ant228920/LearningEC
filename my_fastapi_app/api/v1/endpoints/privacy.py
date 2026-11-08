import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

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


class PrivacyManager:
    """GOD OBJECT (Лаб. №8, Завд. 2, baseline).

    Штучна агрегація: уся розпорошена логіка privacy-модуля зібрана в один клас, що
    одночасно відповідає за авторизацію суб'єкта, експорт даних (GDPR Art. 15),
    анонімізацію (Art. 17), керування згодами, Policy Gate маркетингу, роботу з БД
    та формування відповідей API.
    """

    def __init__(self, db: Session):
        self.db = db
        self.export_schema_version = "1.0"
        self.export_legal_basis = "GDPR Article 15 (Right of Access)"
        self.anon_email_template = "deleted_user_{}@anon.local"
        self.anon_username_template = "deleted_user_{}"
        self.anon_ip = "0.0.0.0"
        self.redacted_password = "[REDACTED_DELETED]"
        self.marketing_purpose = ConsentPurpose.MARKETING_EMAIL

    # ------------------------------------------------------------------ authorization
    def assert_subject(self, user_id: int, actor_id: int, detail: str) -> None:
        if user_id != actor_id:
            logger.warning("Access denied: Actor %s tried to access data of User %s", actor_id, user_id)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    def get_user_or_404(self, user_id: int) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        return user

    # ------------------------------------------------------------------ Right of Access
    def export_personal_data(self, user_id: int, actor_id: int) -> PersonalDataExportResponse:
        self.assert_subject(user_id, actor_id, "Access denied: You are not authorized to export another user's data.")
        user = self.get_user_or_404(user_id)
        profile = UserProfileExport(user_id=user.id, email=user.email, username=user.username, phone=user.phone)
        response = PersonalDataExportResponse(
            export_metadata={
                "schema_version": self.export_schema_version,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "legal_basis": self.export_legal_basis,
            },
            subject_id=user_id,
            profile=profile,
            activity_history=self.export_activities(user_id),
            consents=self.export_consents(user_id),
        )
        logger.info("Personal data export generated successfully for subject_id=%s", user_id)
        return response

    def parse_details(self, raw: Any) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            return {"raw": str(raw)}

    def export_activities(self, user_id: int) -> List[UserActivityExport]:
        rows = self.db.query(UserActivity).filter(UserActivity.user_id == user_id).all()
        return [
            UserActivityExport(action=a.action, timestamp=a.timestamp, details=self.parse_details(a.details))
            for a in rows
        ]

    def export_consents(self, user_id: int) -> List[ConsentExport]:
        rows = self.db.query(UserConsent).filter(UserConsent.user_id == user_id).all()
        return [
            ConsentExport(
                purpose=c.purpose, is_granted=c.is_granted, policy_version=c.policy_version, updated_at=c.updated_at
            )
            for c in rows
        ]

    # ------------------------------------------------------------------ Right to Erasure
    def anonymize(self, user_id: int, actor_id: int) -> AnonymizeResponse:
        self.assert_subject(user_id, actor_id, "Access denied: You cannot anonymize another user's profile.")
        user = self.get_user_or_404(user_id)
        if user.is_anonymized:
            return self.anonymize_response(user_id, "User profile is already anonymized (idempotent response).")
        try:
            self.scrub_user(user, user_id)
            self.mask_activity_ips(user_id)
            self.revoke_all_consents(user_id)
            self.db.commit()
            logger.info("Audit: User subject_id=%s was irreversibly anonymized by actor_id=%s", user_id, actor_id)
        except Exception as e:
            self.db.rollback()
            logger.error("Anonymization failed for user %s: %s", user_id, str(e))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Transaction failed during anonymization workflow.",
            )
        return self.anonymize_response(user_id, "User personal data has been irreversibly anonymized.")

    def anonymize_response(self, user_id: int, message: str) -> AnonymizeResponse:
        return AnonymizeResponse(
            status="success",
            message=message,
            user_id=user_id,
            anonymized_at=datetime.now(timezone.utc).isoformat(),
        )

    def scrub_user(self, user: User, user_id: int) -> None:
        user.email = self.anon_email_template.format(user_id)
        user.username = self.anon_username_template.format(user_id)
        user.phone = None
        user.hashed_password = self.redacted_password
        user.internal_antifraud_score = None
        user.is_anonymized = True

    def mask_activity_ips(self, user_id: int) -> None:
        for act in self.db.query(UserActivity).filter(UserActivity.user_id == user_id).all():
            if act.details:
                self.mask_one_activity(act)

    def mask_one_activity(self, act: UserActivity) -> None:
        try:
            payload = json.loads(act.details) if isinstance(act.details, str) else act.details
            if isinstance(payload, dict) and "ip" in payload:
                payload["ip"] = self.anon_ip
            act.details = json.dumps(payload)
        except Exception:
            pass

    def revoke_all_consents(self, user_id: int) -> None:
        for c in self.db.query(UserConsent).filter(UserConsent.user_id == user_id).all():
            c.is_granted = False
            c.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------ Consent engine
    def grant_consent(self, user_id: int, actor_id: int, req: ConsentUpdateRequest) -> ConsentActionResponse:
        self.assert_subject(user_id, actor_id, "Access denied: Cannot manage consent for another user.")
        consent = self.upsert_consent(user_id, req, granted=True)
        logger.info("Consent granted: user_id=%s purpose=%s version=%s", user_id, req.purpose.value, req.policy_version)
        return self.consent_response(consent)

    def revoke_consent(self, user_id: int, actor_id: int, req: ConsentUpdateRequest) -> ConsentActionResponse:
        self.assert_subject(user_id, actor_id, "Access denied: Cannot manage consent for another user.")
        consent = self.upsert_consent(user_id, req, granted=False)
        logger.info("Consent revoked: user_id=%s purpose=%s", user_id, req.purpose.value)
        return self.consent_response(consent)

    def upsert_consent(self, user_id: int, req: ConsentUpdateRequest, granted: bool) -> UserConsent:
        consent = (
            self.db.query(UserConsent)
            .filter(UserConsent.user_id == user_id, UserConsent.purpose == req.purpose.value)
            .first()
        )
        now_utc = datetime.now(timezone.utc)
        if consent:
            consent.is_granted = granted
            if granted:
                consent.policy_version = req.policy_version
            consent.updated_at = now_utc
        else:
            consent = UserConsent(
                user_id=user_id,
                purpose=req.purpose.value,
                is_granted=granted,
                policy_version=req.policy_version,
                updated_at=now_utc,
            )
            self.db.add(consent)
        self.db.commit()
        self.db.refresh(consent)
        return consent

    def consent_response(self, consent: UserConsent) -> ConsentActionResponse:
        return ConsentActionResponse(
            user_id=consent.user_id,
            purpose=ConsentPurpose(consent.purpose),
            is_granted=consent.is_granted,
            policy_version=consent.policy_version,
            updated_at=consent.updated_at.isoformat(),
        )

    # ------------------------------------------------------------------ Policy Gate
    def send_marketing(self, user_id: int, actor_id: int, body: MarketingCampaignRequest) -> Dict[str, str]:
        self.assert_subject(user_id, actor_id, "Access denied.")
        if not ConsentPolicyGate.check_consent(self.db, user_id, self.marketing_purpose):
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


def get_privacy_manager(db: Session = Depends(get_db)) -> PrivacyManager:
    return PrivacyManager(db)


@privacy_router.get(
    "/{user_id}/personal-data",
    response_model=PersonalDataExportResponse,
    status_code=status.HTTP_200_OK,
    summary="Export User Personal Data (Right of Access)",
)
def export_user_personal_data(
    user_id: int,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    manager: PrivacyManager = Depends(get_privacy_manager),
):
    return manager.export_personal_data(user_id, x_user_id)


@privacy_router.post(
    "/{user_id}/anonymize",
    response_model=AnonymizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Anonymize User Data (Right to Erasure)",
)
def anonymize_user_data(
    user_id: int,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    manager: PrivacyManager = Depends(get_privacy_manager),
):
    return manager.anonymize(user_id, x_user_id)


@privacy_router.post("/{user_id}/consents/grant", response_model=ConsentActionResponse)
def grant_consent(
    user_id: int,
    req: ConsentUpdateRequest,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    manager: PrivacyManager = Depends(get_privacy_manager),
):
    return manager.grant_consent(user_id, x_user_id, req)


@privacy_router.post("/{user_id}/consents/revoke", response_model=ConsentActionResponse)
def revoke_consent(
    user_id: int,
    req: ConsentUpdateRequest,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    manager: PrivacyManager = Depends(get_privacy_manager),
):
    return manager.revoke_consent(user_id, x_user_id, req)


@privacy_router.post("/{user_id}/actions/send-marketing")
def execute_marketing_action(
    user_id: int,
    body: MarketingCampaignRequest,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    manager: PrivacyManager = Depends(get_privacy_manager),
):
    return manager.send_marketing(user_id, x_user_id, body)