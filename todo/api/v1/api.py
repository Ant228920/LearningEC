from fastapi import APIRouter
from api.v1.endpoints import task

api_router = APIRouter()
api_router.include_router(task.router, prefix="/tasks", tags=["Tasks"])