import os
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from schemas.schema import ConvertResponse
from db.session import get_db
from repository.currency_repository import CurrencyRepository
from core.resilience_service import get_external_rate_with_fallback

router = APIRouter()

UPSTREAM_PROVIDER_URL = os.getenv("UPSTREAM_PROVIDER_URL", "http://localhost:9999/api/rate")

@router.get("/api/convert")
def convert_currency(
        amount: float = Query(..., gt=0, description="Сума для конвертації"),
        from_currency: str = Query(..., min_length=3, max_length=3),
        to_currency: str = Query(..., min_length=3, max_length=3),
        db: Session = Depends(get_db)
):
    from_code = from_currency.upper()
    to_code = to_currency.upper()
    repo = CurrencyRepository(db)

    is_degraded = False

    def get_rate(code: str) -> float:
        nonlocal is_degraded
        currency = repo.get_by_code(code)
        if currency:
            return float(currency.rate)

        rate, used_fallback = get_external_rate_with_fallback(code, UPSTREAM_PROVIDER_URL)
        if used_fallback:
            is_degraded = True
        return rate

    from_rate = get_rate(from_code)
    to_rate = get_rate(to_code)

    cross_rate = from_rate / to_rate
    converted = amount * cross_rate

    return {
        "from_currency": from_code,
        "to_currency": to_code,
        "amount": amount,
        "converted_amount": round(converted, 2),
        "cross_rate": round(cross_rate, 4),
        "system_status": "degraded_fallback" if is_degraded else "healthy"
    }