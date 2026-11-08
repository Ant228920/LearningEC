"""Єдина відповідальність: Right to Erasure (GDPR Art. 17) — транзакційна анонімізація."""
import logging
from datetime import datetime, timezone

from schemas.privacy import AnonymizeResponse
from services.privacy.contracts import (
    AnonymizationFailed,
    ConsentStore,
    UnitOfWork,
    UserNotFound,
    UserStore,
)

logger = logging.getLogger("api")

ANON_EMAIL_TEMPLATE = "deleted_user_{}@anon.local"
ANON_USERNAME_TEMPLATE = "deleted_user_{}"
ANON_IP = "0.0.0.0"
MSG_ALREADY = "User profile is already anonymized (idempotent response)."
MSG_DONE = "User personal data has been irreversibly anonymized."


def build_response(user_id: int, message: str) -> AnonymizeResponse:
    return AnonymizeResponse(
        status="success",
        message=message,
        user_id=user_id,
        anonymized_at=datetime.now(timezone.utc).isoformat(),
    )


class AnonymizationService:
    def __init__(self, users: UserStore, consents: ConsentStore, uow: UnitOfWork):
        self._users = users
        self._consents = consents
        self._uow = uow

    def anonymize(self, user_id: int, actor_id: int) -> AnonymizeResponse:
        user = self._users.get(user_id)
        if user is None:
            raise UserNotFound(user_id)
        if user.is_anonymized:
            return build_response(user_id, MSG_ALREADY)
        try:
            self._users.erase_identity(
                user_id, ANON_EMAIL_TEMPLATE.format(user_id), ANON_USERNAME_TEMPLATE.format(user_id)
            )
            self._users.mask_activity_ips(user_id, ANON_IP)
            self._consents.revoke_all(user_id, datetime.now(timezone.utc))
            self._uow.commit()
        except Exception as exc:
            self._uow.rollback()
            logger.error("Anonymization failed for user %s: %s", user_id, str(exc))
            raise AnonymizationFailed(str(exc)) from exc
        logger.info("Audit: User subject_id=%s was irreversibly anonymized by actor_id=%s", user_id, actor_id)
        return build_response(user_id, MSG_DONE)
