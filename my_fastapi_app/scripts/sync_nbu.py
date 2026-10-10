# scripts/sync_nbu.py
import sys
import httpx
from sqlalchemy.orm import Session

from db.session import SessionLocal
from repository.currency_repository import CurrencyRepository

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "PLN": "zł",
}
BLOCKED_CURRENCIES = {"RUB", "BYN"}


def parse_currency_item(item: dict) -> dict | None:
    code = item.get("cc", "")
    name = item.get("txt")
    rate = item.get("rate")

    if not (code and name and rate is not None):
        return None
    if len(code) != 3 or not code.isupper() or code in BLOCKED_CURRENCIES:
        return None

    return {
        "code": code,
        "name": name,
        "rate": float(rate),
        "symbol": CURRENCY_SYMBOLS.get(code, "")
    }


def sync_currencies():
    url = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json"
    print("Завантаження курсів валют з НБУ...")

    try:
        with httpx.Client() as client:
            response = client.get(url, timeout=10.0)
            response.raise_for_status()
            nbu_data = response.json()
    except Exception as e:
        print(f"Помилка при запиті до НБУ: {e}")
        return False

    currencies_data = []
    for item in nbu_data:
        parsed = parse_currency_item(item)
        if parsed:
            currencies_data.append(parsed)

    currencies_data.append({
        "code": "UAH",
        "name": "Українська гривня",
        "rate": 1.0,
        "symbol": "₴"
    })

    db: Session = SessionLocal()
    try:
        repo = CurrencyRepository(db)
        repo.upsert_currencies(currencies_data)
        print(f"Успішно оновлено {len(currencies_data)} валют.")
        return True
    except Exception as e:
        print(f"Помилка запису в базу даних: {e}")
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    if not sync_currencies():
        sys.exit(1)