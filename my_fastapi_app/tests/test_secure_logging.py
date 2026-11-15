import logging
from core.secure_logger import setup_secure_logging

logger = logging.getLogger("api")


def test_secure_logging_masks_pii_and_redacts_secrets(caplog):
    """Позитивний тест: email/телефон частково маскуються, паролі/токени замінюються на [REDACTED]."""
    setup_secure_logging()
    caplog.set_level(logging.INFO)

    raw_email = "student.anton@example.com"
    raw_phone = "+380501234567"
    raw_token = "secret_jwt_bearer_token_xyz"
    raw_password = "SuperSecretPassword123!"

    logger.info(f"Auth attempt: email={raw_email}, phone={raw_phone}, password={raw_password}")
    logger.info("Payload token: %s", {"token": raw_token, "nested": {"email": raw_email}})

    output = caplog.text

    assert raw_email not in output
    assert raw_phone not in output
    assert raw_token not in output
    assert raw_password not in output

    assert "[REDACTED]" in output
    assert "s***@example.com" in output
    assert "+380***4567" in output


def test_secure_logging_sanitizes_exceptions(caplog):
    """Негативний тест: секрети в повідомленнях винятків маскуються логером."""
    setup_secure_logging()
    caplog.set_level(logging.ERROR)

    leaked_secret = "api_key_secret_production_live"
    # Передаємо рядок одразу цілком, без %s та args
    logger.error(f"Failed external API call with token: api_key={leaked_secret}")

    output = caplog.text
    assert leaked_secret not in output
    assert "[REDACTED]" in output