"""Експортери персональних даних: ієрархія наслідування (Лаб. №8, Завд. 3, BASELINE).

Штучна трирівнева ієрархія (за приміткою методички) для демонстрації антипатерну
Inheritance Hell:  BaseExporter -> JsonExporter -> GdprJsonExporter.
Нащадки перевизначають більшість методів і переписують частину батьківської логіки.
"""
import json
import logging
from typing import Any, Dict, List

from services.privacy.contracts import ConsentStore, UserNotFound, UserStore

logger = logging.getLogger("api")


class BaseExporter:
    """Рівень 1: шаблонний метод export() та хуки, які перевизначають нащадки."""

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


class JsonExporter(BaseExporter):
    """Рівень 2: JSON-формат. Перевизначає 4 методи, додає 2."""

    def build_payload(self, profile: Dict[str, Any], activities: List, consents: List) -> Dict[str, Any]:
        payload = super().build_payload(profile, activities, consents)
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


class GdprJsonExporter(JsonExporter):
    """Рівень 3: GDPR Art. 15. Перевизначає 7 методів і переписує половину батьківської логіки."""

    def validate_subject(self, user_id: int) -> None:
        user = self._users.get(user_id)
        if user is None or user.is_anonymized:
            raise UserNotFound(user_id)

    def load_profile(self, user_id: int) -> Dict[str, Any]:
        profile = super().load_profile(user_id)
        profile["phone"] = "***" if profile["phone"] else None
        return profile

    def build_payload(self, profile: Dict[str, Any], activities: List, consents: List) -> Dict[str, Any]:
        return {
            "export_metadata": {"schema_version": self.schema_version(), "legal_basis": self.legal_basis()},
            "profile": profile,
            "activity_history": activities,
            "consents": consents,
        }

    def serialize(self, payload: Dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def content_type(self) -> str:
        return "application/gdpr+json"

    def file_name(self, user_id: int) -> str:
        return f"gdpr_export_{user_id}.json"

    def audit(self, user_id: int) -> None:
        logger.info("GDPR Art.15 export generated for subject_id=%s", user_id)

    def schema_version(self) -> str:
        return "1.0"

    def legal_basis(self) -> str:
        return "GDPR Article 15 (Right of Access)"


def make_base_exporter(users: UserStore, consents: ConsentStore) -> BaseExporter:
    return BaseExporter(users, consents)


def make_json_exporter(users: UserStore, consents: ConsentStore) -> JsonExporter:
    return JsonExporter(users, consents)


def make_gdpr_exporter(users: UserStore, consents: ConsentStore) -> GdprJsonExporter:
    return GdprJsonExporter(users, consents)