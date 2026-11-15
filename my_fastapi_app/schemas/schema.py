from pydantic import BaseModel, Field

class ConvertResponse(BaseModel):
    from_currency: str = None
    to_currency: str = None
    amount: float = 0
    converted_amount: float = 0
    cross_rate: float = 0

    class Config:
        from_attributes = True