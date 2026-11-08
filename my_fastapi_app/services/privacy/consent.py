"""Керування згодами (ConsentService) та їх примусове застосування (ConsentPolicyGate).

Два різні класи, бо це дві різні причини для змін: «як зберігаємо згоду» і «які дії нею захищені».
"""
import logging
from datetime import datetime, timezone

from schemas.privacy import ConsentPurpose
from services.privacy.contracts import ConsentRecord, ConsentStore, UnitOfWork

logger = logging.getLogger("api")


class ConsentService:
    def __init__(self, consents: ConsentStore, uow: UnitOfWork):
        self._consents = consents
        self._uow = uow

    def grant(self, user_id: int, purpose: ConsentPurpose, policy_version: str) -> ConsentRecord:
        saved = self._consents.save(
            ConsentRecord(user_id, purpose.value, True, policy_version, datetime.now(timezone.utc))
        )
        self._uow.commit()
        logger.info("Consent granted: user_id=%s purpose=%s version=%s", user_id, purpose.value, policy_version)
        return saved

    def revoke(self, user_id: int, purpose: ConsentPurpose, policy_version: str) -> ConsentRecord:
        existing = self._consents.find(user_id, purpose.value)
        version = existing.policy_version if existing else policy_version
        saved = self._consents.save(
            ConsentRecord(user_id, purpose.value, False, version, datetime.now(timezone.utc))
        )
        self._uow.commit()
        logger.info("Consent revoked: user_id=%s purpose=%s", user_id, purpose.value)
        return saved


class ConsentPolicyGate:
    """Перевірка активної згоди перед виконанням бізнес-дії."""

    def __init__(self, consents: ConsentStore):
        self._consents = consents

    def check_consent(self, user_id: int, purpose: ConsentPurpose) -> bool:
        record = self._consents.find(user_id, purpose.value)
        return record is not None and record.is_granted
