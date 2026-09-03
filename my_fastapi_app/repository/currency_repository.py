from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from models.currency import Currency


class CurrencyRepository:
    def __init__(self, db: Session):
        self._db = db

    def get_by_code(self, code: str) -> Currency | None:
        return self._db.query(Currency).filter(Currency.code == code).first()

    def upsert_currencies(self, currencies_data: list[dict]) -> None:
        if not currencies_data:
            return

        stmt = insert(Currency).values(currencies_data)

        update_dict = {
            "rate": stmt.excluded.rate,
            "name": stmt.excluded.name,
        }

        on_conflict_stmt = stmt.on_conflict_do_update(
            index_elements=['code'],
            set_=update_dict
        )

        self._db.execute(on_conflict_stmt)
        self._db.commit()