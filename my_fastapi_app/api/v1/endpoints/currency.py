import httpx
from fastapi import APIRouter, HTTPException, Query
from schemas.schema import ConvertResponse

router = APIRouter()


@router.get("/api/convert", response_model=ConvertResponse)
async def convert_currency(
        amount: float = Query(..., gt=0, description="Сума для конвертації"),
        from_currency: str = Query(..., min_length=3, max_length=3),
        to_currency: str = Query(..., min_length=3, max_length=3)
):
    from_code = from_currency.upper()
    to_code = to_currency.upper()

    url = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"

    async with httpx.AsyncClient() as client:
        response = await client.get(url)

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Помилка зв'язку з API НБУ")

    nbu_data = response.json()

    rates = {item["cc"]: item["rate"] for item in nbu_data}
    rates["UAH"] = 1.0

    if from_code not in rates:
        raise HTTPException(status_code=404, detail=f"Валюту {from_code} не знайдено")
    if to_code not in rates:
        raise HTTPException(status_code=404, detail=f"Валюту {to_code} не знайдено")

    cross_rate = rates[from_code] / rates[to_code]
    converted = amount * cross_rate

    return {
        "from_currency": from_code,
        "to_currency": to_code,
        "amount": amount,
        "converted_amount": round(converted, 2),
        "cross_rate": round(cross_rate, 4)
    }