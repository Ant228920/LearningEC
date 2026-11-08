"""SQLAlchemy-адаптери портів з contracts.py.

Єдине місце, яке знає назви ORM-атрибутів (зокрема UserConsent.granted). Усі зміни
схеми моделей локалізуються тут і не поширюються на сервіси.
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models.users import User, UserActivity, UserConsent
from services.privacy.contracts import ActivityRecord, ConsentRecord, UserRecord

REDACTED_PASSWORD = "[REDACTED_DELETED]"


def parse_details(raw: Any) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return {"raw": str(raw)}


def masked_details(raw: Any, mask: str) -> str:
    payload = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(payload, dict) and "ip" in payload:
        payload["ip"] = mask
    return json.dumps(payload)


def mask_failsafe(act: UserActivity, mask: str) -> None:
    try:
        act.details = masked_details(act.details, mask)
    except Exception:
        pass


def fetch_consent_row(db: Session, user_id: int, purpose: str) -> Optional[UserConsent]:
    return db.query(UserConsent).filter(UserConsent.user_id == user_id, UserConsent.purpose == purpose).first()


def to_consent_record(row: UserConsent) -> ConsentRecord:
    return ConsentRecord(
        user_id=row.user_id,
        purpose=row.purpose,
        is_granted=row.granted,
        policy_version=row.policy_version,
        updated_at=row.updated_at,
    )


class SqlUserStore:
    def __init__(self, db: Session):
        self._db = db

    def get(self, user_id: int) -> Optional[UserRecord]:
        row = self._db.query(User).filter(User.id == user_id).first()
        if row is None:
            return None
        return UserRecord(user_id=row.id, email=row.email, username=row.username,
                          phone=row.phone, is_anonymized=bool(row.is_anonymized))

    def list_activities(self, user_id: int) -> List[ActivityRecord]:
        rows = self._db.query(UserActivity).filter(UserActivity.user_id == user_id).all()
        return [ActivityRecord(a.action, a.timestamp, parse_details(a.details)) for a in rows]

    def erase_identity(self, user_id: int, email: str, username: str) -> None:
        user = self._db.query(User).filter(User.id == user_id).one()
        user.email = email
        user.username = username
        user.phone = None
        user.hashed_password = REDACTED_PASSWORD
        user.internal_antifraud_score = None
        user.is_anonymized = True

    def mask_activity_ips(self, user_id: int, mask: str) -> None:
        for act in self._db.query(UserActivity).filter(UserActivity.user_id == user_id).all():
            if act.details:
                mask_failsafe(act, mask)


class SqlConsentStore:
    def __init__(self, db: Session):
        self._db = db

    def find(self, user_id: int, purpose: str) -> Optional[ConsentRecord]:
        row = fetch_consent_row(self._db, user_id, purpose)
        return None if row is None else to_consent_record(row)

    def list_for(self, user_id: int) -> List[ConsentRecord]:
        rows = self._db.query(UserConsent).filter(UserConsent.user_id == user_id).all()
        return [to_consent_record(r) for r in rows]

    def save(self, record: ConsentRecord) -> ConsentRecord:
        row = fetch_consent_row(self._db, record.user_id, record.purpose)
        if row is None:
            row = UserConsent(user_id=record.user_id, purpose=record.purpose)
            self._db.add(row)
        row.granted = record.is_granted
        row.policy_version = record.policy_version
        row.updated_at = record.updated_at
        self._db.flush()
        self._db.refresh(row)
        return to_consent_record(row)

    def revoke_all(self, user_id: int, at: datetime) -> None:
        for row in self._db.query(UserConsent).filter(UserConsent.user_id == user_id).all():
            row.granted = False
            row.updated_at = at


class SqlUnitOfWork:
    def __init__(self, db: Session):
        self._db = db

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()
