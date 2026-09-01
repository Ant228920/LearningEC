from sqlalchemy import Column, Integer, String
from db.session import Base

class Currency(Base):
    __tablename__ = 'currencies'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    symbol = Column(String, nullable=False)