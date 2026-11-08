"""Маршрут Right of Access (GDPR Art. 15)."""
from fastapi import APIRouter, Depends, Header, HTTPException, status

from api.v1.privacy_deps import get_export_service, require_subject
from schemas.privacy import PersonalDataExportResponse
from services.privacy.contracts import UserNotFound
from services.privacy.data_export import DataExportService

export_router = APIRouter()


@export_router.get(
    "/{user_id}/personal-data",
    response_model=PersonalDataExportResponse,
    status_code=status.HTTP_200_OK,
    summary="Export User Personal Data (Right of Access)",
)
def export_user_personal_data(
    user_id: int,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    service: DataExportService = Depends(get_export_service),
):
    require_subject(user_id, x_user_id, "Access denied: You are not authorized to export another user's data.")
    try:
        return service.export(user_id)
    except UserNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.") from None
