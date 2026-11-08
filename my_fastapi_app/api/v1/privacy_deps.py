"""Composition root Privacy API: єдине місце, де інтерфейси зв'язуються з SQL-реалізаціями."""
import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.session import get_db
from services.privacy.anonymization import AnonymizationService
from services.privacy.consent import ConsentPolicyGate, ConsentService
from services.privacy.data_export import DataExportService
from services.privacy.sql_adapters import SqlConsentStore, SqlUnitOfWork, SqlUserStore

logger = logging.getLogger("api")


def get_export_service(db: Session = Depends(get_db)) -> DataExportService:
    return DataExportService(SqlUserStore(db), SqlConsentStore(db))


def get_anonymization_service(db: Session = Depends(get_db)) -> AnonymizationService:
    return AnonymizationService(SqlUserStore(db), SqlConsentStore(db), SqlUnitOfWork(db))


def get_consent_service(db: Session = Depends(get_db)) -> ConsentService:
    return ConsentService(SqlConsentStore(db), SqlUnitOfWork(db))


def get_policy_gate(db: Session = Depends(get_db)) -> ConsentPolicyGate:
    return ConsentPolicyGate(SqlConsentStore(db))


def require_subject(user_id: int, actor_id: int, detail: str) -> None:
    if user_id != actor_id:
        logger.warning("Access denied: Actor %s tried to access data of User %s", actor_id, user_id)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
