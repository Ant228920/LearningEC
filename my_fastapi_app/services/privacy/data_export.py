"""Єдина відповідальність: Right of Access (GDPR Art. 15) — збір пакета персональних даних."""
import logging
from datetime import datetime, timezone

from schemas.privacy import (
    ConsentExport,
    PersonalDataExportResponse,
    UserActivityExport,
    UserProfileExport,
)
from services.privacy.contracts import ConsentStore, UserNotFound, UserStore

logger = logging.getLogger("api")

EXPORT_SCHEMA_VERSION = "1.0"
EXPORT_LEGAL_BASIS = "GDPR Article 15 (Right of Access)"


class DataExportService:
    def __init__(self, users: UserStore, consents: ConsentStore):
        self._users = users
        self._consents = consents

    def export(self, user_id: int) -> PersonalDataExportResponse:
        user = self._users.get(user_id)
        if user is None:
            raise UserNotFound(user_id)
        response = PersonalDataExportResponse(
            export_metadata={
                "schema_version": EXPORT_SCHEMA_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "legal_basis": EXPORT_LEGAL_BASIS,
            },
            subject_id=user_id,
            profile=UserProfileExport(
                user_id=user.user_id, email=user.email, username=user.username, phone=user.phone
            ),
            activity_history=[
                UserActivityExport(action=a.action, timestamp=a.timestamp, details=a.details)
                for a in self._users.list_activities(user_id)
            ],
            consents=[
                ConsentExport(
                    purpose=c.purpose, is_granted=c.is_granted,
                    policy_version=c.policy_version, updated_at=c.updated_at,
                )
                for c in self._consents.list_for(user_id)
            ],
        )
        logger.info("Personal data export generated successfully for subject_id=%s", user_id)
        return response
