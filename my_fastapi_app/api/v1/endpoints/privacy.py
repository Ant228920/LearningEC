"""Агрегатор Privacy API: збирає SRP-роутери під єдиним префіксом /users.

Публічне ім'я `privacy_router` збережене, тому main.py змін не потребує.
"""
from fastapi import APIRouter

from api.v1.endpoints.privacy_consent import consent_router
from api.v1.endpoints.privacy_erasure import erasure_router
from api.v1.endpoints.privacy_export import export_router

privacy_router = APIRouter(prefix="/users", tags=["Privacy & GDPR"])
privacy_router.include_router(export_router)
privacy_router.include_router(erasure_router)
privacy_router.include_router(consent_router)
