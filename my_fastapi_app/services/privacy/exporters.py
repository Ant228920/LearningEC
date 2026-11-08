"""Експортери персональних даних: КОМПОЗИЦІЯ замість наслідування (Лаб. №8, Завд. 3, PASS).

Було:  BaseExporter -> JsonExporter -> GdprJsonExporter   (extends, DIT=3, 7 перевизначень)
Стало: JsonExporter ВОЛОДІЄ BaseExporter, GdprJsonExporter ВОЛОДІЄ JsonExporter
       (приватне поле, Dependency Injection через конструктор, делегування викликів).
Зміна в «батьківському» класі більше не ламає «нащадків» автоматично.
"""
import json
import logging
from typing import Any, Dict, List

from services.privacy.contracts import ConsentStore, UserNotFound, UserStore

logger = logging.getLogger("api")


class BaseExporter:
    """Базовий компонент: завантаження даних та сирий payload. Більше нікого не «успадковує»."""

    def __init__(self, users: UserStore, consents: ConsentStore):
        self._users = users
        self._consents = consents

    def export(self, user_id: int) -> Any:
        self.validate_subject(user_id)
        bundle = {
            "profile": self.load_profile(user_id),
            "activities": self.load_activities(user_id),
            "consents": self.load_consents(user_id),
        }
        payload = self.build_payload(bundle)
        self.audit(user_id)
        return self.serialize(payload)

    def validate_subject(self, user_id: int) -> None:
        if self._users.get(user_id) is None:
            raise UserNotFound(user_id)

    def load_profile(self, user_id: int) -> Dict[str, Any]:
        user = self._users.get(user_id)
        return {"user_id": user.user_id, "email": user.email, "username": user.username, "phone": user.phone}

    def load_activities(self, user_id: int) -> List[Dict[str, Any]]:
        return [
            {"action": a.action, "timestamp": a.timestamp.isoformat(), "details": a.details}
            for a in self._users.list_activities(user_id)
        ]

    def load_consents(self, user_id: int) -> List[Dict[str, Any]]:
        return [
            {"purpose": c.purpose, "is_granted": c.is_granted, "policy_version": c.policy_version}
            for c in self._consents.list_for(user_id)
        ]

    def build_payload(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        return dict(bundle)

    def serialize(self, payload: Dict[str, Any]) -> Any:
        return payload

    def content_type(self) -> str:
        return "application/octet-stream"

    def file_name(self, user_id: int) -> str:
        return f"export_{user_id}.bin"

    def audit(self, user_id: int) -> None:
        logger.info("Export generated: subject_id=%s", user_id)


class JsonExporter:
    """JSON-формат. Тримає BaseExporter у приватному полі та делегує йому завантаження даних."""

    def __init__(self, base: BaseExporter):
        self._base = base

    def export(self, user_id: int) -> str:
        self._base.validate_subject(user_id)
        bundle = {
            "profile": self._base.load_profile(user_id),
            "activities": self._base.load_activities(user_id),
            "consents": self._base.load_consents(user_id),
        }
        payload = self.build_payload(bundle)
        self._base.audit(user_id)
        return self.serialize(payload)

    def load_profile(self, user_id: int) -> Dict[str, Any]:
        return self._base.load_profile(user_id)

    def load_activities(self, user_id: int) -> List[Dict[str, Any]]:
        return self._base.load_activities(user_id)

    def load_consents(self, user_id: int) -> List[Dict[str, Any]]:
        return self._base.load_consents(user_id)

    def build_payload(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        payload = self._base.build_payload(bundle)
        payload["format"] = "json"
        return payload

    def serialize(self, payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=True)

    def content_type(self) -> str:
        return "application/json"

    def file_name(self, user_id: int) -> str:
        return f"export_{user_id}.json"

    def to_json(self, user_id: int) -> str:
        return self.export(user_id)

    def parse(self, text: str) -> Dict[str, Any]:
        return json.loads(text)


class GdprJsonExporter:
    """GDPR Art. 15. Тримає JsonExporter (завантаження) і UserStore (перевірка суб'єкта) як залежності."""

    def __init__(self, json_exporter: JsonExporter, users: UserStore):
        self._json = json_exporter
        self._users = users

    def export(self, user_id: int) -> str:
        self._ensure_exportable(user_id)
        payload = {
            "export_metadata": {"schema_version": self.schema_version(), "legal_basis": self.legal_basis()},
            "profile": self._masked_profile(user_id),
            "activity_history": self._json.load_activities(user_id),
            "consents": self._json.load_consents(user_id),
        }
        logger.info("GDPR Art.15 export generated for subject_id=%s", user_id)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def content_type(self) -> str:
        return "application/gdpr+json"

    def file_name(self, user_id: int) -> str:
        return f"gdpr_export_{user_id}.json"

    def schema_version(self) -> str:
        return "1.0"

    def legal_basis(self) -> str:
        return "GDPR Article 15 (Right of Access)"

    def _ensure_exportable(self, user_id: int) -> None:
        user = self._users.get(user_id)
        if user is None or user.is_anonymized:
            raise UserNotFound(user_id)

    def _masked_profile(self, user_id: int) -> Dict[str, Any]:
        profile = self._json.load_profile(user_id)
        profile["phone"] = "***" if profile["phone"] else None
        return profile


def make_base_exporter(users: UserStore, consents: ConsentStore) -> BaseExporter:
    return BaseExporter(users, consents)


def make_json_exporter(users: UserStore, consents: ConsentStore) -> JsonExporter:
    return JsonExporter(BaseExporter(users, consents))


def make_gdpr_exporter(users: UserStore, consents: ConsentStore) -> GdprJsonExporter:
    return GdprJsonExporter(make_json_exporter(users, consents), users)