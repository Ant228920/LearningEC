from fastapi import FastAPI

from api.api import api_router
from core.secure_logger import setup_secure_logging
from db.session import engine, Base
import logging

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="TODO List API",
    description="REST API для управління завданнями",
    version="1.0.0"
)

app.include_router(api_router, prefix="/api/v1")

logger = logging.getLogger("api")

setup_secure_logging()

@app.post("/api/v1/auth/test-login-log")
async def demo_login_log(data: dict):
    logger.info(f"User login attempt: email={data.get('email')}, phone={data.get('phone')}, token={data.get('token')}")
    return {"status": "ok"}