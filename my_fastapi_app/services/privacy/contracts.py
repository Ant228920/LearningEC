"""Контракти privacy-підсистеми (Dependency Inversion).

Сервіси залежать ВИКЛЮЧНО від цих абстракцій та нейтральних records. Про SQLAlchemy,
ORM-моделі, FastAPI і HTTP вони нічого не знають, тому зміна моделі (наприклад,
перейменування UserConsent.is_granted) не доходить до бізнес-логіки.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class UserRecord:
    user_id: int
    email: str
    username: str
    phone: Optional[str]
    is_anonymized: bool


@dataclass(frozen=True)
class ActivityRecord:
    action: str
    timestamp: datetime
    details: Dict[str, Any]


@dataclass(frozen=True)
class ConsentRecord:
    user_id: int
    purpose: str
    is_granted: bool
    policy_version: str
    updated_at: datetime


class UserNotFound(Exception):
    """Суб'єкта даних не знайдено."""


class AnonymizationFailed(Exception):
    """Транзакція анонімізації відкотена."""


class UserStore(Protocol):
    def get(self, user_id: int) -> Optional[UserRecord]: ...

    def list_activities(self, user_id: int) -> List[ActivityRecord]: ...

    def erase_identity(self, user_id: int, email: str, username: str) -> None: ...

    def mask_activity_ips(self, user_id: int, mask: str) -> None: ...


class ConsentStore(Protocol):
    def find(self, user_id: int, purpose: str) -> Optional[ConsentRecord]: ...

    def list_for(self, user_id: int) -> List[ConsentRecord]: ...

    def save(self, record: ConsentRecord) -> ConsentRecord: ...

    def revoke_all(self, user_id: int, at: datetime) -> None: ...


class UnitOfWork(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...
