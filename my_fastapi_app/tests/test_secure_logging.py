import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
import pytest
from core.secure_logger import PIISanitizingFilter, sanitize_message


def test_sanitize_direct_string():
    """Тест позитивного сценарію: пряма санітизація тексту"""
    raw_message = (
        "User registered: email=test.user@company.com, "
        "phone=+380991234567, password=SuperSecretPassword123, "
        "token=ghp_ABC123XYZ" # gitleaks:allow
    )
    sanitized = sanitize_message(raw_message)

    # 1. Перевіряємо маскування PII (код країни та останні 4 цифри)
    assert "t***@company.com" in sanitized
    assert "+380***4567" in sanitized

    # 2. Перевіряємо повне видалення секретів
    assert "password=[REDACTED]" in sanitized
    assert "token=[REDACTED]" in sanitized

    # 3. Перевіряємо відсутність сирих даних
    assert "test.user@company.com" not in sanitized
    assert "+380991234567" not in sanitized
    assert "SuperSecretPassword123" not in sanitized
    assert "ghp_ABC123XYZ" not in sanitized


def test_logging_filter_interception(caplog):
    """
    Інтеграційний тест: перевірка централізованого перехоплення logging.LogRecord
    через вбудовану фікстуру pytest caplog.
    """
    logger = logging.getLogger("test_logger")
    logger.setLevel(logging.INFO)
    logger.addFilter(PIISanitizingFilter())

    sensitive_email = "victim@example.org"
    sensitive_secret = "VeryPrivateToken999"

    # Викликаємо звичайне логування
    with caplog.at_level(logging.INFO):
        logger.info(f"Failed transaction for account={sensitive_email} with secret={sensitive_secret}")

    captured_logs = caplog.text

    # Переконуємося, що в результуючий вивід логу не потрапило жодне сире значення
    assert sensitive_email not in captured_logs
    assert sensitive_secret not in captured_logs

    # Переконуємося, що фільтр спрацював
    assert "v***@example.org" in captured_logs
    assert "secret=[REDACTED]" in captured_logs


def test_exception_message_sanitization():
    try:
        raise ValueError("Connection failed for credentials user=admin@corp.ua password=db_root_pass")
    except Exception as exc:
        sanitized_exc = sanitize_message(str(exc))
        assert "admin@corp.ua" not in sanitized_exc
        assert "db_root_pass" not in sanitized_exc
        assert "password=[REDACTED]" in sanitized_exc