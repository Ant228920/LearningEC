from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session
from schemas.schema import ConvertResponse
from db.session import get_db
from repository.currency_repository import CurrencyRepository

router = APIRouter()


@router.get("/api/convert", response_model=ConvertResponse)
def convert_currency(
        amount: float = Query(..., gt=0, description="Сума для конвертації"),
        from_currency: str = Query(..., min_length=3, max_length=3),
        to_currency: str = Query(..., min_length=3, max_length=3),
        db: Session = Depends(get_db)
):
    from_code = from_currency.upper()
    to_code = to_currency.upper()

    repo = CurrencyRepository(db)

    def get_rate(code: str) -> float:

        currency = repo.get_by_code(code)
        if not currency:
            raise HTTPException(status_code=404, detail=f"Валюту {code} не знайдено в базі")

        return float(currency.rate)

    from_rate = get_rate(from_code)
    to_rate = get_rate(to_code)

    cross_rate = from_rate / to_rate
    converted = amount * cross_rate

    return {
        "from_currency": from_code,
        "to_currency": to_code,
        "amount": amount,
        "converted_amount": round(converted, 2),
        "cross_rate": round(cross_rate, 4)
    }