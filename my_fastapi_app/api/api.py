from fastapi import APIRouter
from api.v1.endpoints import currency

api_router = APIRouter()
api_router.include_router(currency.router, prefix="/tasks", tags=["Tasks"])