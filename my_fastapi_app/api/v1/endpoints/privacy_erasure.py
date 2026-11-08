"""Маршрут Right to Erasure (GDPR Art. 17)."""
from fastapi import APIRouter, Depends, Header, HTTPException, status

from api.v1.privacy_deps import get_anonymization_service, require_subject
from schemas.privacy import AnonymizeResponse
from services.privacy.anonymization import AnonymizationService
from services.privacy.contracts import AnonymizationFailed, UserNotFound

erasure_router = APIRouter()


@erasure_router.post(
    "/{user_id}/anonymize",
    response_model=AnonymizeResponse,
    status_code=status.HTTP_200_OK,
    summary="Anonymize User Data (Right to Erasure)",
)
def anonymize_user_data(
    user_id: int,
    x_user_id: int = Header(..., description="ID авторизованого користувача"),
    service: AnonymizationService = Depends(get_anonymization_service),
):
    require_subject(user_id, x_user_id, "Access denied: You cannot anonymize another user's profile.")
    try:
        return service.anonymize(user_id, x_user_id)
    except UserNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.") from None
    except AnonymizationFailed:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction failed during anonymization workflow.",
        ) from None
