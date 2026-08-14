from fastapi import FastAPI

from api.v1.api import api_router
from db.session import engine, Base
from models.task import Task

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TODO List API",
    description="REST API для управління завданнями",
    version="1.0.0"
)

app.include_router(api_router, prefix="/api/v1")