from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from db.session import get_db
from repository.currency_repository import CurrencyRepository
from schemas.schema import ConvertResponse

router = APIRouter()


@router.get("/api/convert", response_model=ConvertResponse)
def convert_currency(
        amount: float = Query(..., gt=0, description="Сума для конвертації"),
        from_currency: str = Query(..., min_length=3, max_length=3),
        to_currency: str = Query(..., min_length=3, max_length=3),
        db: Session = Depends(get_db)
):
    repo = CurrencyRepository(db)

    from_code = from_currency.upper()
    to_code = to_currency.upper()

    # Шукаємо валюти у власній базі даних (включно з UAH)
    curr_from = repo.get_by_code(from_code)
    curr_to = repo.get_by_code(to_code)

    if not curr_from:
        raise HTTPException(status_code=404, detail=f"Валюту {from_code} не знайдено в базі")
    if not curr_to:
        raise HTTPException(status_code=404, detail=f"Валюту {to_code} не знайдено в базі")

    # Рахуємо крос-курс на основі даних з БД
    cross_rate = curr_from.rate / curr_to.rate
    converted = amount * cross_rate

    return {
        "from_currency": from_code,
        "to_currency": to_code,
        "amount": amount,
        "converted_amount": round(converted, 2),
        "cross_rate": round(cross_rate, 4)
    }