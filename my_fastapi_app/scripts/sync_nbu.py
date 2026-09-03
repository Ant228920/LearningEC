# scripts/sync_nbu.py
import sys
import httpx
from sqlalchemy.orm import Session

from db.session import SessionLocal
from repository.currency_repository import CurrencyRepository


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
        sys.exit(1)

    currencies_data = []
    for item in nbu_data:
        currencies_data.append({
            "code": item["cc"],
            "name": item["txt"],
            "rate": item["rate"],
            "symbol": ""
        })

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
    except Exception as e:
        print(f"Помилка запису в базу даних: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    sync_currencies()